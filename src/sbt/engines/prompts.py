"""Prompt builders, one per model family. PROMPT_VERSION is part of the cache key."""
from __future__ import annotations

import json

from sbt import languages
from sbt.engines.base import TranslationItem, TranslationRequest

PROMPT_VERSION = "p1.3"

DOMAIN = ("smart buildings, building management systems (BMS/BAS), HVAC, energy management, IoT, "
          "building automation, electrical and facility management, cloud and IT systems")

TAG_RULE = ("The text contains formatting tags like <g1>…</g1>. Keep every tag exactly once, wrapped around "
            "the translated words they belong to. Do not add, remove, rename or translate tags.")
PLACEHOLDER_RULE = "Keep placeholders like <x1/> unchanged."


def _ja_style(item: TranslationItem, tgt: str) -> str:
    if tgt != "ja":
        return ""
    return ("Use concise noun-ending style (体言止め) suitable for a slide title or bullet."
            if item.is_heading else "Use polite です・ます style.")


def hymt_messages(req: TranslationRequest, item: TranslationItem,
                  previous: list[tuple[str, str]] | None = None) -> list[dict[str, str]]:
    """Hy-MT2's documented templates (background + terminology + style), combined.

    `previous` = lines of the same slide already translated, so numbering and wording stay consistent.
    """
    tgt = languages.get(req.target_lang).name
    parts: list[str] = []
    if req.context or previous:
        background = list(req.context)
        if previous:
            background.append("Lines of this slide already translated (keep the same wording and numbering "
                              "style):")
            background += [f"{s} => {t}" for s, t in previous[-6:]]
        parts.append("[Background Information]\n" + "\n".join(background) + "\n")
    if item.hints:
        parts.append("Reference the following translations:\n"
                     + "\n".join(f"{h.source} translates to {h.target}" for h in item.hints) + "\n")
    rules = [r for r in (
        _ja_style(item, req.target_lang),
        TAG_RULE if "<g" in item.text else "",
        PLACEHOLDER_RULE if "<x" in item.text else "",
        item.feedback,
    ) if r]
    instruction = f"Please translate the following text into {tgt}"
    instruction += ", taking the provided background information into consideration." if req.context else "."
    if rules:
        instruction += "\n" + "\n".join(rules)
    instruction += "\nNote that you must ONLY output the translated result without any additional explanation:"
    parts.append(f"{instruction}\n\n{item.text}")
    return [{"role": "user", "content": "\n".join(parts)}]


def cat_messages(req: TranslationRequest, item: TranslationItem) -> list[dict[str, str]]:
    """CAT-Translate documents a single fixed prompt; extra instructions are not part of its training."""
    src = languages.get(req.source_lang).name
    tgt = languages.get(req.target_lang).name
    return [{"role": "user", "content": f"Translate the following {src} text into {tgt}.\n\n{item.text}"}]


QWEN_SYSTEM = """You are a professional technical translator specialising in {domain}.
Translate from {src} to {tgt}.

Rules:
1. Translate meaning accurately, as a domain engineer would write it. Never translate word-by-word.
2. When a segment has "terms", use exactly those target terms.
3. Keep product names, protocol names, acronyms, model/part numbers, URLs, e-mail addresses, IP addresses,
   file paths, numbers and units unchanged.
4. {tag_rule} {placeholder_rule}
5. "context" is for understanding only; do not translate it.
6. {style}
7. Output JSON only, one translation per input id."""


def qwen_messages(req: TranslationRequest) -> list[dict[str, str]]:
    src = languages.get(req.source_lang).name
    tgt = languages.get(req.target_lang).name
    style = ("For Japanese: titles and bullet fragments use concise noun-ending style (体言止め); full sentences "
             "use です・ます. Use Japanese punctuation 、。 and keep half-width Latin letters and digits."
             if req.target_lang == "ja" else "Use natural, professional technical style.")
    system = QWEN_SYSTEM.format(domain=DOMAIN, src=src, tgt=tgt, tag_rule=TAG_RULE,
                                placeholder_rule=PLACEHOLDER_RULE, style=style)
    payload = {
        "context": req.context,
        "segments": [
            {"id": it.id, "text": it.text,
             **({"terms": {h.source: h.target for h in it.hints}} if it.hints else {}),
             **({"style": "heading" if it.is_heading else "sentence"}),
             **({"previous_attempt_problem": it.feedback} if it.feedback else {})}
            for it in req.items
        ],
    }
    return [{"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)}]


def qwen_schema(ids: list[str]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"translations": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"id": {"type": "string", "enum": ids}, "text": {"type": "string"}},
                      "required": ["id", "text"]},
        }},
        "required": ["translations"],
    }
