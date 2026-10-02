"""Runs one translation job in a background thread; the window polls its state."""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from sbt.app import jobs
from sbt.app.jobs import STAGES, JobCancelled, JobSpec, TranslationJob
from sbt.domain.models import DocumentError
from sbt.settings import Settings

log = logging.getLogger("sbt.ui")


@dataclass
class JobState:
    status: str = "idle"                 # idle | running | done | failed | cancelled
    stage: str = ""
    stages_done: list[str] = field(default_factory=list)
    done: int = 0
    total: int = 0
    error: str = ""
    started: float = 0.0
    finished: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return {"status": self.status, "stage": self.stage, "stage_label": STAGES.get(self.stage, ""),
                "stages_done": list(self.stages_done), "done": self.done, "total": self.total,
                "error": self.error, "elapsed": round((self.finished or time.time()) - self.started, 1)
                if self.started else 0}


class UiReporter(jobs.Reporter):
    def __init__(self, state: JobState, cancel: threading.Event) -> None:
        self.state = state
        self.cancel = cancel

    def stage(self, key: str) -> None:
        self._check()
        if self.state.stage and self.state.stage not in self.state.stages_done and self.state.stage != key:
            self.state.stages_done.append(self.state.stage)
        self.state.stage = key

    def progress(self, done: int, total: int) -> None:
        self._check()
        self.state.done, self.state.total = done, total

    def _check(self) -> None:
        if self.cancel.is_set():
            raise JobCancelled()


# Seen in the UI: messages for errors a user can act on (no stack traces, no document text).
_FRIENDLY = {
    FileNotFoundError: "The translation engine or model is not installed. Open Models to install it.",
    PermissionError: "The output file could not be written. Is it open in PowerPoint or a PDF viewer? "
                     "Close it and try again.",
    TimeoutError: "The translation engine did not start in time. Try again, or switch to CPU in Settings.",
}


class JobRunner:
    def __init__(self, run: Callable[..., TranslationJob] = jobs.run) -> None:
        self._run = run                           # injectable for tests
        self.state = JobState()
        self.job: TranslationJob | None = None
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return self.state.status == "running"

    def start(self, spec: JobSpec, settings: Settings, use_memory: bool) -> None:
        if self.busy:
            raise RuntimeError("A translation is already running")
        self.state = JobState(status="running", started=time.time())
        self.job = None
        self._cancel.clear()
        reporter = UiReporter(self.state, self._cancel)
        self._thread = threading.Thread(target=self._work, args=(spec, settings, use_memory, reporter),
                                        daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def _work(self, spec: JobSpec, settings: Settings, use_memory: bool, reporter: UiReporter) -> None:
        try:
            self.job = self._run(spec, settings, use_memory=use_memory, reporter=reporter)
            if self.state.stage:
                self.state.stages_done.append(self.state.stage)
            self.state.status = "done"
        except JobCancelled:
            self.state.status = "cancelled"
        except DocumentError as e:
            self.state.status, self.state.error = "failed", str(e)
        except (FileNotFoundError, PermissionError, TimeoutError) as e:
            self.state.status, self.state.error = "failed", _FRIENDLY[type(e)]
        except Exception as e:                  # never show a traceback to the user; log the type only
            log.exception("Job failed")
            self.state.status = "failed"
            self.state.error = f"The translation failed ({type(e).__name__}). Details are in the log."
        finally:
            self.state.finished = time.time()
