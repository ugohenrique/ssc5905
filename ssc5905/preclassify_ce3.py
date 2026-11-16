#!/usr/bin/env python3
"""
preclassify_ce3.py — Pré-classifica os secundários antes da revisão manual.

Correção v2: trata NaN/None/float na coluna document_type.
"""
import argparse
import re
import pandas as pd

EXPLICIT_TITLE_RE = re.compile(
    r"^\s*(?:an?\s+)?"
    r"(?:"
    r"(?:comprehensive|systematic|critical|brief|detailed|extensive|"
    r"practical|theoretical|recent)\s+"
    r")?"
    r"(?:survey|review|overview|mapping|taxonomy|tutorial)\b",
    re.IGNORECASE,
)

COLON_TITLE_RE = re.compile(
    r":\s*(?:an?\s+)?(?:survey|review|overview|mapping|taxonomy|tutorial)\s*$",
    re.IGNORECASE,
)

SEC_DOC_TYPES = {"review", "survey", "conference review",
                 "tutorial", "taxonomy", "overview", "editorial"}


def _safe_str(x) -> str:
    """Converte NaN/None/float/str para string segura (vazia se nulo)."""
    if x is None:
        return ""
    if isinstance(x, float):
        return ""
    return str(x).strip()


def classify(title, doc_type):
    t = _safe_str(title)
    dt = _safe_str(doc_type).lower()

    if not t:
        return "revisar", "título vazio"

    if EXPLICIT_TITLE_RE.search(t):
        return "secundario", "título começa com survey/review/overview/mapping/taxonomy/tutorial"

    if COLON_TITLE_RE.search(t):
        return "secundario", "título termina com ': a survey/review/overview'"

    if dt in SEC_DOC_TYPES:
        return "secundario", f"document_type='{_safe_str(doc_type)}'"

    return "revisar", "heurística inconclusiva"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auditoria", default="auditoria_ce3.csv")
    ap.add_argument("--output", default="auditoria_ce3_preenchida.csv")
    args = ap.parse_args()

    df = pd.read_csv(args.auditoria, dtype=str, keep_default_na=False)
    # keep_default_na=False força pandas a NÃO converter vazios em NaN.
    # Ainda assim mantemos _safe_str por segurança.

    decisions, reasons = [], []
    for _, row in df.iterrows():
        d, r = classify(row["title"], row["document_type"])
        decisions.append(d)
        reasons.append(r)
    df["decisao"] = decisions
    df["motivo_auto"] = reasons

    df.to_csv(args.output, index=False, encoding="utf-8")

    counts = df["decisao"].value_counts()
    print(f"Arquivo gerado: {args.output}")
    print(f"Total: {len(df)}")
    for k, v in counts.items():
        print(f"  {k:<12} {v}")

    print("\nCasos a revisar manualmente (filtre 'revisar' na coluna 'decisao'):")
    revisar = df[df["decisao"] == "revisar"]
    if len(revisar):
        for _, r in revisar.iterrows():
            title = _safe_str(r["title"])
            print(f"  [{r['source_row']}] {title[:90]}")
    else:
        print("  (nenhum)")


if __name__ == "__main__":
    main()