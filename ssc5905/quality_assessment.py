#!/usr/bin/env python3
"""
quality_assessment.py — Avaliação de qualidade DARE-adaptada (0-10).

Lê estudos_incluidos.csv e gera quality_scores.csv com 10 critérios
(CQ1..CQ10), score total e classificação (High/Medium/Low).

CQ1  aims clearly stated
CQ2  method reproducible
CQ3  design justified
CQ4  explicitly addresses >=1 axis
CQ5  results substantiated
CQ6  relation to prior work discussed
CQ7  limitations discussed
CQ8  calibration metrics reported
CQ9  variability across seeds reported
CQ10 distinguishes epistemic vs. aleatoric uncertainty

Heurísticas (NÃO VINCULANTES — revisar manualmente):
  - CQ1: abstract tem "we propose/we present/we introduce"
  - CQ2: abstract menciona dataset/code/algorithm/reproducib
  - CQ3: abstract menciona motivation/why/justify
  - CQ4: regex dos 3 eixos (qualquer match)
  - CQ5: abstract menciona results/experiments/evaluation
  - CQ6: abstract menciona prior/previous/existing/related
  - CQ7: abstract menciona limitation/future work
  - CQ8: abstract menciona calibration/ECE/Brier/NLL
  - CQ9: abstract menciona seed/variance/std/error bars
  - CQ10: abstract menciona epistemic/aleatoric

Uso:
    python quality_assessment.py --input estudos_incluidos.csv
    python quality_assessment.py --stats
"""

import argparse
import re
import pandas as pd

CRITERIOS = [
    ("CQ1_aims",      r"\b(we (propose|present|introduce|develop|design)|this (paper|work) (proposes|presents))",
     "we propose/present/introduce"),
    ("CQ2_repro",     r"\b(dataset|code|algorithm|reproducib|available at|github|publicly)",
     "dataset/code/algorithm"),
    ("CQ3_design",    r"\b(motivat|justif|rationale|why we|because)",
     "motivation/justification"),
    ("CQ4_axis",      r"\b(incomplet|open.?world|owa|uncertain|probabilistic|variational|"
                      r"bayesian|calibrat|inconsisten|contradict|noisy|granular)",
     ">=1 uncertainty axis"),
    ("CQ5_results",   r"\b(experiment|evaluation|result|benchmark|outperform|improv)",
     "results/experiments"),
    ("CQ6_prior",     r"\b(prior|previous|existing|related|state.?of.?the.?art|recent)",
     "prior work discussed"),
    ("CQ7_limits",    r"\b(limitation|future work|open (issue|problem)|challenge)",
     "limitations discussed"),
    ("CQ8_calib",     r"\b(calibrat|ece|brier|nll|expected calibration|confidence interval)",
     "calibration metrics"),
    ("CQ9_seeds",     r"\b(seed|variance|standard deviation|std|error bar|multiple runs)",
     "variability across seeds"),
    ("CQ10_uncert",   r"\b(epistemic|aleatoric|both types|two types of uncertainty)",
     "epistemic vs aleatoric"),
]


def safe(s):
    return s if isinstance(s, str) else ""


def score_row(row):
    text = f" {safe(row.get('title',''))} {safe(row.get('abstract',''))} {safe(row.get('author_keywords',''))} ".lower()
    scores = {}
    for name, pat, _desc in CRITERIOS:
        scores[name] = 1 if re.search(pat, text) else 0
    total = sum(scores.values())
    if total >= 8:
        label = "High"
    elif total >= 5:
        label = "Medium"
    else:
        label = "Low"
    return scores, total, label


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="estudos_incluidos.csv")
    ap.add_argument("--output", default="quality_scores.csv")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    if args.stats:
        df = pd.read_csv(args.output, dtype=str, keep_default_na=False)
        print(f"Total de estudos avaliados: {len(df)}")
        print()
        print("Distribuição de qualidade:")
        for label in ["High", "Medium", "Low"]:
            n = (df["quality_label"] == label).sum()
            print(f"  {label:<8} {n:>4} ({100*n/max(len(df),1):.1f}%)")
        print()
        print("Score médio por critério:")
        for name, _, desc in CRITERIOS:
            if name in df.columns:
                n = (df[name] == "1").sum()
                print(f"  {name:<18} {n:>4} ({100*n/max(len(df),1):.1f}%)  [{desc}]")
        print()
        print(f"Score médio total: {df['quality_score'].astype(float).mean():.2f}/10")
        return

    df = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    rows = []
    for _, r in df.iterrows():
        scores, total, label = score_row(r)
        row = {
            "source_row": r.get("source_row", ""),
            "title": r.get("title", ""),
            "year": r.get("year", ""),
        }
        row.update(scores)
        row["quality_score"] = total
        row["quality_label"] = label
        row["justificativa"] = ""  # revisão manual
        rows.append(row)

    out = pd.DataFrame(rows)
    out.to_csv(args.output, index=False, encoding="utf-8")

    print(f"Avaliação gerada: {args.output} ({len(out)} estudos)")
    print()
    print("Distribuição de qualidade:")
    for label in ["High", "Medium", "Low"]:
        n = (out["quality_label"] == label).sum()
        print(f"  {label:<8} {n:>4} ({100*n/max(len(out),1):.1f}%)")
    print()
    print("Score médio por critério:")
    for name, _, desc in CRITERIOS:
        n = (out[name] == 1).sum()
        print(f"  {name:<18} {n:>4} ({100*n/max(len(out),1):.1f}%)  [{desc}]")
    print()
    print(f"Score médio total: {out['quality_score'].mean():.2f}/10")
    print()
    print("Instruções:")
    print("  1. Abra quality_scores.csv e revise os 10 critérios")
    print("  2. Ajuste os scores heurísticos manualmente (CQ1..CQ10)")
    print("  3. Recalcule 'quality_score' e 'quality_label' após ajustes")
    print("  4. Rode novamente com --stats")


if __name__ == "__main__":
    main()