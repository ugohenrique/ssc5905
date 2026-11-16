#!/usr/bin/env python3
"""
extract_data.py — Formulário de extração de dados (§10.2 do protocolo v9).

Lê estudos_incluidos.csv (238 registros), gera extracao_dados.csv
com colunas de identificação, eixos, fragmentação, mecanismo,
benchmarks, métricas, tipo de incerteza e relação com VKGI.

Heurísticas (NÃO VINCULANTES) pré-preenchem a maioria das colunas
a partir do título + abstract + author_keywords. A revisão manual
consiste em:
  1. Confirmar/corrigir os eixos (0/1)
  2. Confirmar/corrigir o fragmentation_level (0/1/2)
  3. Confirmar/corrigir mecanismo e benchmarks
  4. Preencher 'uncertainty_type' (epistemic/aleatoric/both)
  5. Preencher 'relation_to_VKGI' (1 frase)
  6. Mesclar 'quality_score' de quality_scores.csv (se existir)

Uso:
    python extract_data.py --input estudos_incluidos.csv
    # revisar extracao_dados.csv
    python extract_data.py --stats
"""

import argparse
import os
import re
import pandas as pd

# ----------------------------------------------------------------------
# Padrões para detecção dos eixos
# ----------------------------------------------------------------------
EIXOS = {
    "incompletude": (
        r"\b(incomplet|open[- ]world|owa|missing|few[- ]shot|sparse|"
        r"incomplete knowledge|under[- ]specified)\b"
    ),
    "contradicao": (
        r"\b(inconsisten|contradict|conflict|noisy|error[ -]detection|"
        r"paraconsistent|refine|noise[ -]aware|error[ -]aware)\b"
    ),
    "granularidade": (
        r"\b(calibrat|uncertain|probabilistic|variational|bayesian|"
        r"gaussian|confidence|evidential|conformal|"
        r"predictive distribution|normalizing flow|neural process)\b"
    ),
}

# ----------------------------------------------------------------------
# Mecanismos
# ----------------------------------------------------------------------
MECANISMOS = {
    "variational_inference": r"\bvariational|elbo|kl[ -]divergence|amortized",
    "bayesian":              r"\bbayesian|posterior|prior|dirichlet",
    "gaussian_embedding":    r"\bgaussian|normal distribution|mean and variance",
    "evidential":            r"\bevidential|dempster|dirichlet",
    "normalizing_flow":      r"\bnormalizing flow|\bnf[ -]",
    "neural_process":        r"\bneural process|\bnp[ -]",
    "fuzzy_logic":           r"\bfuzzy|t[ -]norm|tsk|anfis",
    "paraconsistent":        r"\bparaconsistent|four[ -]valued|belnap",
    "inconsistency_aware":   r"\binconsistency[ -]aware|error[ -]aware",
    "conformal_prediction":  r"\bconformal",
    "graph_neural_network":  r"\bgraph neural network|\bgnn\b|\bgcn\b|\bgat\b",
    "knowledge_graph_embedding": r"\bknowledge graph embedding|\bkge\b",
    "box_embedding":         r"\bbox embedding|axis[ -]aligned",
    "cone_embedding":        r"\bcone embedding|cone semantics",
    "query_embedding":       r"\bquery embedding|logical query",
}

# ----------------------------------------------------------------------
# Benchmarks
# ----------------------------------------------------------------------
BENCHMARKS = {
    "FB15k-237":  r"fb15k[ -]?237",
    "WN18RR":     r"wn18rr",
    "WN18":       r"\bwn18\b",
    "FB15k":      r"\bfb15k\b(?![- ]?237)",
    "DBpedia":    r"dbpedia",
    "YAGO":       r"yago",
    "Wikidata":   r"wikidata",
    "NELL":       r"\bnell\b",
    "Freebase":   r"freebase",
    "SNOMED CT":  r"snomed",
    "CN15k":      r"cn15k",
    "Hetionet":   r"hetionet",
    "MIMIC-III":  r"mimic[ -]?iii",
    "MIMIC-IV":   r"mimic[ -]?iv",
    "Cora":       r"\bcora\b",
    "PubMed":     r"pubmed",
    "WordNet":    r"wordnet",
    "UMLS":       r"\bumls\b",
    "Bio2RDF":    r"bio2rdf",
    "DBpedia-1B": r"1\s?billion triples|dbpedia.*billion",
}

# ----------------------------------------------------------------------
# Métricas
# ----------------------------------------------------------------------
METRICAS = {
    "MRR":       r"\bmrr\b|mean reciprocal rank",
    "Hits@k":    r"hits@|hit@",
    "MR":        r"\bmr\b|mean rank",
    "AUC":       r"\bauc\b|area under",
    "AUPRC":     r"auprc|precision[ -]recall curve",
    "F1":        r"\bf1\b|f[ -]measure",
    "ECE":       r"\bece\b|expected calibration error",
    "Brier":     r"\bbrier\b",
    "NLL":       r"\bnll\b|negative log[ -]likelihood",
    "Accuracy":  r"\baccuracy\b",
    "Recall@k":  r"recall@",
    "Precision@k": r"precision@",
    "NDCG@k":    r"ndcg@",
    "MAE":       r"\bmae\b|mean absolute error",
    "RMSE":      r"\brmse\b|root mean squared",
    "MSE":       r"\bmse\b|mean squared error",
    "Jaccard":   r"jaccard",
    "CohenKappa": r"cohen.?s kappa|kappa",
}

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def safe(s):
    if s is None:
        return ""
    if isinstance(s, float):
        return ""
    return str(s)


def build_text(row):
    return f" {safe(row.get('title',''))} " \
           f"{safe(row.get('abstract',''))} " \
           f"{safe(row.get('author_keywords',''))} ".lower()


def detect_eixos(text):
    return {k: int(bool(re.search(p, text))) for k, p in EIXOS.items()}


def detect_mecanismos(text):
    return [k for k, p in MECANISMOS.items() if re.search(p, text)]


def detect_benchmarks(text):
    return [k for k, p in BENCHMARKS.items() if re.search(p, text)]


def detect_metricas(text):
    return [k for k, p in METRICAS.items() if re.search(p, text)]


def infer_fragmentation(axes):
    n = sum(axes.values())
    if n <= 1:
        return 0
    # Level 2 só se o abstract declarar acoplamento explícito
    # (heurística conservadora — assume Level 1; revisão manual promove a 2)
    return 1


def infer_uncertainty_type(text):
    epi = bool(re.search(r"\bepistemic|model uncertainty|knowledge uncertainty", text))
    ale = bool(re.search(r"\baleatoric|data noise|observation noise", text))
    if epi and ale:
        return "both"
    if epi:
        return "epistemic"
    if ale:
        return "aleatoric"
    return ""


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="estudos_incluidos.csv")
    ap.add_argument("--output", default="extracao_dados.csv")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    # Fase 2 — estatísticas
    if args.stats:
        if not os.path.exists(args.output):
            print(f"Arquivo não encontrado: {args.output}")
            return
        df = pd.read_csv(args.output, dtype=str, keep_default_na=False)
        print("=" * 60)
        print("ESTATÍSTICAS DE EXTRAÇÃO")
        print("=" * 60)
        print(f"Total de estudos incluídos: {len(df)}")
        print()
        print("Eixos (contagem de 1s):")
        for k in EIXOS:
            col = f"axis_{k}"
            if col in df.columns:
                n = (df[col] == "1").sum()
                print(f"  {col:<25} {n:>4} ({100*n/max(len(df),1):.1f}%)")
        print()
        print("Fragmentação:")
        if "fragmentation_level" in df.columns:
            for lvl in ["0", "1", "2"]:
                n = (df["fragmentation_level"] == lvl).sum()
                print(f"  Level {lvl}: {n:>4} ({100*n/max(len(df),1):.1f}%)")
        print()
        print("Tipo de incerteza:")
        if "uncertainty_type" in df.columns:
            for t in ["epistemic", "aleatoric", "both", ""]:
                n = (df["uncertainty_type"] == t).sum()
                label = t or "(não preenchido)"
                print(f"  {label:<20} {n:>4}")
        print()
        print("Mecanismos mais frequentes:")
        if "mechanism" in df.columns:
            from collections import Counter
            cnt = Counter()
            for m in df["mechanism"]:
                for item in str(m).split(","):
                    item = item.strip()
                    if item:
                        cnt[item] += 1
            for k, v in cnt.most_common(10):
                print(f"  {k:<30} {v:>4}")
        print()
        print("Benchmarks mais frequentes:")
        if "benchmarks" in df.columns:
            from collections import Counter
            cnt = Counter()
            for m in df["benchmarks"]:
                for item in str(m).split(","):
                    item = item.strip()
                    if item:
                        cnt[item] += 1
            for k, v in cnt.most_common(10):
                print(f"  {k:<20} {v:>4}")
        print()
        print("Métricas mais frequentes:")
        if "metrics" in df.columns:
            from collections import Counter
            cnt = Counter()
            for m in df["metrics"]:
                for item in str(m).split(","):
                    item = item.strip()
                    if item:
                        cnt[item] += 1
            for k, v in cnt.most_common(10):
                print(f"  {k:<20} {v:>4}")
        print("=" * 60)
        return

    # Fase 1 — gerar a planilha
    if not os.path.exists(args.input):
        print(f"Arquivo não encontrado: {args.input}")
        return

    df = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    print(f"Estudos incluídos lidos: {len(df)}")

    rows = []
    for _, r in df.iterrows():
        text = build_text(r.to_dict())
        axes = detect_eixos(text)
        mecs = detect_mecanismos(text)
        benchs = detect_benchmarks(text)
        metrics = detect_metricas(text)
        frag = infer_fragmentation(axes)
        unc_type = infer_uncertainty_type(text)

        rows.append({
            "study_id": r.get("source_row", ""),
            "source_row": r.get("source_row", ""),
            "title": r.get("title", ""),
            "year": r.get("year", ""),
            "doi": r.get("doi", ""),
            "venue": r.get("journal", "") or r.get("source", ""),
            "axis_incompletude": axes["incompletude"],
            "axis_contradicao": axes["contradicao"],
            "axis_granularidade": axes["granularidade"],
            "fragmentation_level": frag,
            "mechanism": ", ".join(mecs),
            "benchmarks": ", ".join(benchs),
            "metrics": ", ".join(metrics),
            "uncertainty_type": unc_type,
            "relation_to_VKGI": "",   # preencher manualmente (1 frase)
            "quality_score": "",      # mesclado de quality_scores.csv se existir
            "quality_label": "",
            "notes": "",
        })

    out = pd.DataFrame(rows)

    # Mescla quality_scores.csv se existir
    if os.path.exists("quality_scores.csv"):
        q = pd.read_csv("quality_scores.csv", dtype=str, keep_default_na=False)
        cols_q = [c for c in ["source_row", "quality_score", "quality_label"]
                  if c in q.columns]
        if len(cols_q) >= 2:
            out = out.merge(q[cols_q], on="source_row", how="left",
                            suffixes=("", "_q"))
            # Se já existir quality_score na out, prioriza a de quality_scores
            if "quality_score_q" in out.columns:
                out["quality_score"] = out["quality_score_q"].fillna(out["quality_score"])
                out = out.drop(columns=["quality_score_q"])
            if "quality_label_q" in out.columns:
                out["quality_label"] = out["quality_label_q"].fillna(out["quality_label"])
                out = out.drop(columns=["quality_label_q"])
            print("Quality scores mesclados de quality_scores.csv")

    out.to_csv(args.output, index=False, encoding="utf-8")

    print(f"Extração gerada: {args.output} ({len(out)} estudos)")
    print()
    print("Pré-preenchimento heurístico:")
    for k in EIXOS:
        n = int(out[f"axis_{k}"].sum())
        print(f"  axis_{k:<18} {n:>4} ({100*n/len(out):.1f}%)")
    print()
    print("Distribuição de fragmentação:")
    for lvl in ["0", "1", "2"]:
        n = (out["fragmentation_level"] == lvl).sum()
        print(f"  Level {lvl}: {n:>4}")
    print()
    print("Tipo de incerteza (heurística):")
    for t in ["epistemic", "aleatoric", "both", ""]:
        n = (out["uncertainty_type"] == t).sum()
        label = t or "(não detectado)"
        print(f"  {label:<20} {n:>4}")
    print()
    print("Instruções:")
    print("  1. Abra extracao_dados.csv no Excel/LibreOffice")
    print("  2. Revise 'axis_*', 'fragmentation_level', 'mechanism', 'benchmarks', 'metrics'")
    print("  3. Preencha 'uncertainty_type' (epistemic/aleatoric/both) nos vazios")
    print("  4. Preencha 'relation_to_VKGI' (1 frase por estudo)")
    print("  5. Mescle 'quality_score' de quality_scores.csv (se já rodou)")
    print("  6. Rode novamente com --stats")


if __name__ == "__main__":
    main()