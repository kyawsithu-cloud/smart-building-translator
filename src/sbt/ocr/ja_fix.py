"""Japanese OCR clean-up.

The bundled multilingual recogniser is shared with Chinese, so it sometimes returns the simplified-Chinese form
of a character that Japanese writes differently (値 → 值). Every character on the left does not exist in
Japanese text encoding (cp932), so replacing it cannot damage correct Japanese.
"""
from __future__ import annotations

import re

SIMPLIFIED_TO_JA = {
    "值": "値", "设": "設", "计": "計", "电": "電", "气": "気", "冻": "凍", "统": "統", "时": "時", "间": "間",
    "备": "備", "调": "調", "节": "節", "动": "動", "态": "態", "报": "報", "监": "監", "视": "視", "测": "測",
    "运": "運", "转": "転", "输": "輸", "压": "圧", "负": "負", "载": "載", "热": "熱", "换": "換", "风": "風",
    "门": "門", "阀": "閥", "网": "網", "络": "絡", "线": "線", "图": "図", "库": "庫", "码": "碼", "类": "類",
    "级": "級", "页": "頁", "项": "項", "题": "題", "单": "単", "发": "発", "开": "開", "关": "関", "闭": "閉",
    "东": "東", "车": "車", "层": "層", "场": "場", "厂": "廠", "产": "産", "业": "業", "务": "務", "检": "検",
    "验": "験", "试": "試", "编": "編", "辑": "輯", "启": "啓", "确": "確", "认": "認", "说": "説", "明": "明",
    "长": "長", "宽": "寛", "离": "離", "远": "遠", "进": "進", "过": "過", "还": "還", "这": "這", "个": "個",
    "们": "們", "为": "為", "与": "与", "从": "従", "将": "将", "对": "対", "应": "応", "显": "顕", "示": "示",
    "传": "伝", "感": "感", "器": "器", "湿": "湿", "环": "環", "境": "境", "能": "能", "耗": "耗", "费": "費",
    "预": "予", "警": "警", "维": "維", "护": "護", "保": "保", "养": "養", "装": "装", "置": "置", "号": "号",
}


def _not_japanese(ch: str) -> bool:
    try:
        ch.encode("cp932")
        return False
    except UnicodeEncodeError:
        return True


# Old (traditional) forms that modern technical Japanese does not use; OCR sometimes returns them (温 → 溫).
KYUJITAI_TO_JA = {
    "\u6eab": "\u6e29", "\u6c23": "\u6c17", "\u9ad4": "\u4f53", "\u7576": "\u5f53", "\u5716": "\u56f3",
    "\u6578": "\u6570", "\u8655": "\u51e6", "\u8b8a": "\u5909", "\u8f49": "\u8ee2", "\u7d93": "\u7d4c",
    "\u5be6": "\u5b9f", "\u50f9": "\u4fa1", "\u55ae": "\u5358", "\u767c": "\u767a", "\u6703": "\u4f1a",
    "\u5b78": "\u5b66", "\u6a23": "\u69d8", "\u64f4": "\u62e1", "\u6aa2": "\u691c", "\u6fd5": "\u6e7f",
    "\u58d3": "\u5727", "\u5ee3": "\u5e83", "\u61c9": "\u5fdc", "\u9ede": "\u70b9", "\u9435": "\u9244",
    "\u7e3d": "\u7dcf", "\u7d1a": "\u7d1a", "\u9a57": "\u9a13", "\u8b77": "\u8b77",
}
SIMPLIFIED_TO_JA.update(KYUJITAI_TO_JA)

# Only keep mappings whose source really is absent from Japanese encoding and whose target is valid Japanese.
_MAP = {k: v for k, v in SIMPLIFIED_TO_JA.items() if len(k) == 1 and k != v and not _not_japanese(v)
        and (_not_japanese(k) or k in KYUJITAI_TO_JA)}
_TABLE = str.maketrans(_MAP)


# 机 is valid Japanese ("desk"), but after another kanji it is OCR's simplified form of 機 (冷凍机 → 冷凍機).
_KI = re.compile(r"(?<=[\u4e00-\u9fff])机")


# Kanji/katakana look-alikes inside katakana words: エ/工, ロ/口, カ/力, ニ/二, ー/一, タ/夕, ト/卜, ハ/八.
# Replaced only when followed by katakana and not preceded by a kanji (工場, 人工 stay as they are).
_LOOKALIKE = str.maketrans({"\u5de5": "\u30a8", "\u53e3": "\u30ed", "\u529b": "\u30ab", "\u4e8c": "\u30cb",
                            "\u4e00": "\u30fc", "\u5915": "\u30bf", "\u535c": "\u30c8", "\u516b": "\u30cf"})
_IN_KATAKANA = re.compile(r"(?<![\u4e00-\u9fff])[\u5de5\u53e3\u529b\u4e8c\u4e00\u5915\u535c\u516b](?=[\u30a1-\u30fa])")


def fix(text: str) -> str:
    text = _KI.sub("\u6a5f", text.translate(_TABLE))
    return _IN_KATAKANA.sub(lambda m: m.group(0).translate(_LOOKALIKE), text)


def suspicious(text: str) -> int:
    """Characters that cannot be Japanese text after fixing (likely OCR errors)."""
    return sum(_not_japanese(c) for c in text if ord(c) > 0x2E80)
