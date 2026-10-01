"""Engine backed by a local llama.cpp `llama-server` (OpenAI-compatible API on 127.0.0.1)."""
from __future__ import annotations

import json
import re
import time
from urllib.parse import urlparse

import httpx

from sbt.engines import prompts
from sbt.engines.base import (EngineInfo, EngineStats, TranslationItem, TranslationRequest,
                              TranslationResult)
from sbt.engines.profiles import ModelProfile
from sbt.pipeline.tags import strip_tags

_THINK = re.compile(r"<think>.*?</think>\s*", re.S)


class LlamaCppEngine:
    def __init__(self, profile: ModelProfile, base_url: str, timeout: float = 600.0) -> None:
        host = urlparse(base_url).hostname
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("LlamaCppEngine only talks to a server on this computer")
        self.profile = profile
        self._client = httpx.Client(base_url=base_url, timeout=timeout, trust_env=False)  # ignore proxies
        self.stats = EngineStats()

    @property
    def info(self) -> EngineInfo:
        return EngineInfo(f"llamacpp:{self.profile.id}", self.profile.file, True, self.profile.languages)

    def _chat(self, messages: list[dict[str, str]], extra: dict[str, object] | None = None) -> str:
        body: dict[str, object] = {"messages": messages, "stream": False, **self.profile.sampling, **(extra or {})}
        start = time.perf_counter()
        r = self._client.post("/v1/chat/completions", json=body)
        r.raise_for_status()
        data = r.json()
        self.stats.calls += 1
        self.stats.seconds += time.perf_counter() - start
        usage = data.get("usage") or {}
        self.stats.prompt_tokens += usage.get("prompt_tokens", 0)
        self.stats.completion_tokens += usage.get("completion_tokens", 0)
        return _THINK.sub("", data["choices"][0]["message"].get("content") or "").strip()

    def _one(self, req: TranslationRequest, item: TranslationItem, previous: list[tuple[str, str]]) -> str:
        messages = (prompts.cat_messages(req, item) if self.profile.prompt_style == "cat"
                    else prompts.hymt_messages(req, item, previous))
        return self._chat(messages, {"max_tokens": max(256, len(item.text) * 4)})

    def translate(self, request: TranslationRequest) -> TranslationResult:
        out: dict[str, str] = {}
        failed: list[str] = []
        if self.profile.prompt_style == "qwen_json":
            ids = [it.id for it in request.items]
            try:
                raw = self._chat(prompts.qwen_messages(request), {
                    "max_tokens": 256 + sum(len(it.text) for it in request.items) * 4,
                    "response_format": {"type": "json_schema",
                                        "json_schema": {"name": "t", "schema": prompts.qwen_schema(ids)}},
                })
                for row in json.loads(raw).get("translations", []):
                    if row.get("id") in ids:
                        out[row["id"]] = row.get("text", "")
            except (json.JSONDecodeError, httpx.HTTPError):
                pass
            failed = [i for i in ids if not out.get(i)]
        else:
            previous = [(strip_tags(s), strip_tags(t)) for s, t in request.previous]
            for item in request.items:
                try:
                    out[item.id] = self._one(request, item, previous)
                    previous.append((strip_tags(item.text), strip_tags(out[item.id])))
                except httpx.HTTPError:
                    failed.append(item.id)
        return TranslationResult(out, failed)
