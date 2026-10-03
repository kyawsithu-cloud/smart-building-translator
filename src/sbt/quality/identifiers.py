"""Identifiers and numbers that must survive translation unchanged.

  token_changed    an identifier was altered (192.168.1.100 → 192.168.1.10, FX-PCG2611 → FX-PCG2161)
  token_missing    an identifier is gone
  token_added      a URL / e-mail / IP / part number appears that is not in the original paragraph
  number_changed   a number or unit is missing or different (24 °C → 42 °C, kW → W)
"""
from __future__ import annotations

import re
from collections import Counter

from rapidfuzz import fuzz

from sbt.domain.models import Severity
from sbt.protection import tokens as tok
from sbt.quality.context import Pair
from sbt.quality.findings import Finding

# Units compared after normalising notation (℃ = °C, ％ = %, ㎡ = m2 = m²).
_UNIT = re.compile(r"(?<=\d)\s?(°\s?[CF]|℃|℉|%|％|kWh|MWh|GWh|Wh|kW|MW|W|kVA|VA|kV|V|mA|A|Hz|kHz|kPa|MPa|Pa|"
                   r"ppm|dB|lx|lux|m2|m²|㎡|m3/h|m³/h|L/s|l/s|CFM|cfm|rpm|mm|cm|km|m|kg|t|s|ms|min|h)(?![A-Za-z0-9])")
_UNIT_NORM = {"℃": "°C", "℉": "°F", "％": "%", "㎡": "m²", "m2": "m²", "m3/h": "m³/h", "l/s": "L/s",
              "cfm": "CFM", "lux": "lx"}


def _units(text: str) -> Counter[str]:
    """How often each unit follows a number. Counted, not just collected: in "from 24 °C to 26 °C", turning one
    of them into °F must still be noticed."""
    out: Counter[str] = Counter()
    for m in _UNIT.finditer(text):
        u = m.group(1).replace(" ", "")
        out[_UNIT_NORM.get(u, u)] += 1
    for ambiguous in ("m", "s", "h", "t", "A", "W", "V", "min"):   # one-letter units are too ambiguous in prose
        out.pop(ambiguous, None)
    return out


# Units written out in the target language are correct localisation, not a changed unit (Chinese 兆瓦时 = MWh).
_SPELLED = {
    "kWh": ["キロワット時", "千瓦时", "千瓦時", "กิโลวัตต์-ชั่วโมง", "กิโลวัตต์ชั่วโมง", "킬로와트시", "Kilowattstunde"],
    "MWh": ["メガワット時", "兆瓦时", "兆瓦時", "เมกะวัตต์-ชั่วโมง", "เมกะวัตต์ชั่วโมง", "메가와트시", "Megawattstunde"],
    "GWh": ["ギガワット時", "吉瓦时", "กิกะวัตต์-ชั่วโมง", "기가와트시"],
    "kW": ["キロワット", "千瓦", "กิโลวัตต์", "킬로와트"],
    "MW": ["メガワット", "兆瓦", "เมกะวัตต์", "메가와트"],
    "ppm": ["百万分之", "ส่วนในล้านส่วน", "พีพีเอ็ม"],
    "°C": [r"\d\s*度", "摄氏", "攝氏", "องศาเซลเซียส", r"\d\s*องศา", "섭씨", r"\d\s*도", "ဒီဂရီ"],   # not 温度 (temperature)
    "%": ["パーセント", "百分之", "เปอร์เซ็นต์", "퍼센트", "ရာခိုင်နှုန်း"],
    "m²": ["平方メートル", "平方米", "平方公尺", "ตารางเมตร", "제곱미터"],
    "kPa": ["キロパスカル", "千帕", "กิโลปาสกาล", "킬로파스칼"],
    "Hz": ["ヘルツ", "赫兹", "เฮิรตซ์", "헤르츠"],
    "lx": ["ルクス", "勒克斯", "ลักซ์", "럭스"],
}


def _lost_units(source: str, target: str) -> list[str]:
    have = _units(target)
    lost = []
    for unit, count in _units(source).items():
        spelled = sum(len(re.findall(w, target, re.IGNORECASE)) for w in _SPELLED.get(unit, []))
        if have[unit] + spelled < count:
            lost.append(unit)
    return sorted(lost)


def _opaque(token: str) -> bool:
    return bool(tok.OPAQUE_RE.fullmatch(token))


def _without(text: str, tokens: list[str]) -> str:
    for t in sorted(tokens, key=len, reverse=True):
        text = text.replace(t, " ")
    return text


def check(pairs: list[Pair]) -> list[Finding]:
    found: list[Finding] = []
    for p in pairs:
        if p.kept or not p.target.strip():
            continue
        one = ([p.seg.id], [p.seg.container])
        out_tokens = tok.protected_tokens(p.target, [])
        for t in p.protected:
            if t in p.target:
                continue
            near = max(((fuzz.ratio(t, o), o) for o in out_tokens
                        if o not in p.protected and _opaque(o) == _opaque(t)), default=(0.0, ""))
            if near[0] >= 70:
                found.append(Finding("identifiers", "token_changed", Severity.ERROR,
                                     f"{p.where}: identifier changed", *one, detail={"from": t, "to": near[1]}))
            else:
                found.append(Finding("identifiers", "token_missing",
                                     Severity.ERROR if _opaque(t) else Severity.WARNING,
                                     f"{p.where}: identifier missing", *one, detail={"missing": t}))
        added = [o for o in out_tokens if _opaque(o) and o not in p.source
                 and not any(o in t or t in o for t in p.protected)]
        if added:
            found.append(Finding("identifiers", "token_added", Severity.WARNING,
                                 f"{p.where}: identifier not in the original", *one, detail={"added": added}))

        src_rest, tgt_rest = _without(p.source, p.protected), _without(p.target, p.protected)
        lost = tok.significant_numbers(src_rest) - tok.significant_numbers(tgt_rest)
        lost_units = _lost_units(src_rest, tgt_rest)
        if lost or lost_units:
            new = sorted(tok.significant_numbers(tgt_rest) - tok.significant_numbers(src_rest))
            found.append(Finding("identifiers", "number_changed", Severity.WARNING,
                                 f"{p.where}: number or unit missing or changed", *one,
                                 detail={"missing": sorted(lost) + lost_units, "new": new}))
    return found
