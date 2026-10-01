"""Term consistency on the consistency decks, measured from the review sheets.

For each planted term: in every paragraph that contains it, which translation variant was used?
  consistency = share of occurrences using the most common variant ("other" = no known variant found)
  acceptable  = share of occurrences using an acceptable variant
Variant lists are the evaluator's (Claude's) judgement and are part of this file so they can be reviewed.

    py scripts/consistency_eval.py eval/results/phase2/hy-mt2-7b
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

# source term -> (acceptable variants, other known variants)
EN_JA: dict[str, tuple[list[str], list[str]]] = {
    "chilled water plant": (["冷水プラント"], ["冷水設備", "冷却水プラント", "チルド水プラント", "冷水熱源", "冷水機プラント"]),
    "free cooling": (["フリークーリング"], ["無料冷却", "無料の冷却", "フリー冷却", "自然冷却", "外気冷却"]),
    "load shedding": (["負荷遮断", "負荷制限", "ロードシェディング", "負荷削減"], ["負荷の削減", "負荷軽減", "負荷カット"]),
    "fault detection and diagnostics": (
        ["故障検知・診断", "故障検出・診断", "故障検知と診断", "故障検出と診断", "故障検知および診断", "故障検出および診断",
         "故障の検出と診断", "故障の検知と診断", "故障検知診断", "故障検出診断"], ["障害検出と診断", "障害検知・診断"]),
    "demand-controlled ventilation": (["デマンド制御換気", "需要制御換気", "需要対応型換気", "デマンド換気"],
                                      ["需要制御型換気", "需要に応じた換気", "デマンドコントロール換気"]),
    "supply air temperature": (["給気温度"], ["供給空気温度", "吹出温度", "送風温度", "供給空気の温度", "吹き出し温度"]),
    "condenser water": (["冷却水"], ["凝縮水", "コンデンサー水", "復水", "凝縮器水"]),
    "trend log": (["トレンドログ"], ["傾向ログ", "トレンド記録", "履歴ログ", "トレンドデータ"]),
    "heat recovery": (["熱回収"], ["排熱回収", "熱の回収", "廃熱回収"]),
    "point list": (["ポイントリスト"], ["点リスト", "ポイント一覧", "点一覧"]),
}
JA_EN: dict[str, tuple[list[str], list[str]]] = {
    "冷水プラント": (["chilled water plant", "chilled-water plant"], ["cold water plant", "chilled water system",
                                                                  "chiller plant", "chilled water facility"]),
    "フリークーリング": (["free cooling", "free-cooling"], ["natural cooling"]),
    "負荷遮断": (["load shedding"], ["load shed", "load cut", "load interruption", "load disconnection",
                                 "load curtailment", "load reduction"]),
    "故障検知・診断": (["fault detection and diagnostics", "fault detection and diagnosis",
                     "fault detection & diagnostics"], ["failure detection and diagnosis", "fault detection"]),
    "デマンド制御換気": (["demand-controlled ventilation", "demand controlled ventilation"],
                    ["demand control ventilation", "demand-based ventilation"]),
    "給気温度": (["supply air temperature"], ["supply temperature", "discharge air temperature",
                                         "air supply temperature"]),
    "冷却水": (["condenser water", "cooling water"], ["chilled water"]),
    "トレンドログ": (["trend log"], ["trend record", "trend data"]),
    "熱回収": (["heat recovery"], ["heat reclaim", "waste heat"]),
    "ポイントリスト": (["point list", "points list"], ["point table"]),
}


def _variant(text: str, table: tuple[list[str], list[str]]) -> str:
    low = text.lower()
    for v in sorted(table[0] + table[1], key=len, reverse=True):
        if v.lower() in low:
            return v
    return "other"


def score(review_csv: Path, table: dict[str, tuple[list[str], list[str]]]) -> list[tuple[str, int, float, float, str]]:
    rows = list(csv.DictReader(review_csv.open(encoding="utf-8-sig")))
    out = []
    for term, variants in table.items():
        rx = re.compile(re.escape(term), re.IGNORECASE)
        used = [_variant(re.sub(r"</?g\d+>", "", r["translation"]), variants)
                for r in rows if rx.search(r["source"])]
        if not used:
            continue
        counts = Counter(used)
        top, top_n = counts.most_common(1)[0]
        ok = sum(n for v, n in counts.items() if v in variants[0])
        out.append((term, len(used), top_n / len(used), ok / len(used), ", ".join(f"{v}×{n}" for v, n in
                                                                                  counts.most_common())))
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    folder = Path(sys.argv[1])
    summary = []
    for review in sorted(folder.glob("consistency_*.review.csv")):
        if "_en-ja_" not in review.name and "_ja-en_" not in review.name:
            continue                       # variant tables exist for English↔Japanese only
        table = EN_JA if "_en-ja_" in review.name else JA_EN
        rows = score(review, table)
        n = sum(r[1] for r in rows)
        cons = sum(r[1] * r[2] for r in rows) / n
        acc = sum(r[1] * r[3] for r in rows) / n
        summary.append((review.stem, cons, acc))
        print(f"\n## {review.stem}: consistency {cons:.0%}, acceptable {acc:.0%} over {n} occurrences")
        for term, k, c, a, detail in rows:
            print(f"  {term:<32} n={k}  consistent {c:.0%}  acceptable {a:.0%}   {detail}")
    print("\n| run | consistency | acceptable |\n|---|---|---|")
    for name, c, a in summary:
        print(f"| {name} | {c:.0%} | {a:.0%} |")


if __name__ == "__main__":
    main()
