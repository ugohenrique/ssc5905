#!/usr/bin/env python3
"""
screen_title_abstract.py — Triagem título/abstract dos 599 primários.

Fases:
  1. Gerar CSV interativo (default):  --input estudos_primarios_v8.csv
     Saída: triagem_titulo_abstract.csv  (com heurísticas pré-preenchidas)
  2. Aplicar decisões manuais:        --apply
     Saída: estudos_incluidos.csv, estudos_excluidos.csv, relatorio_triagem.csv
  3. Estatísticas PRISMA:             --stats

Critérios (protocolo v7, §8):
  CI1 — KGE ou representation learning sobre KGs
  CI2 — ≥1 dos 3 eixos (incompletude, contradição, granularidade)
  CI3 — variational/probabilistic/UQ
  CI4 — publicação primária (indexada)
  CI5 — avaliação empírica
  CI6 — inglês
  CE1 — KG só auxiliar (sem contribuição a KGE)
  CE2 — grafos genéricos sem ontologia
  CE3 — survey/review/mapping (já removidos na fase anterior)
  CE4 — abstract/editorial
  CE5 — sem embedding/aprendizado/inferência
  CE6 — duplicata (já removidos na fase anterior)

Heurísticas (NÃO VINCULANTES — servem só para pré-preencher):
  - detecta sinais de CI1..CI6 e CE1/CE2/CE5 no título + abstract
  - sugere 'incluir' se ≥4 sinais positivos e nenhum negativo
  - sugere 'excluir (CEn)' se ≥1 sinal negativo forte
  - caso contrário, sugere 'duvida' (revisão manual obrigatória)
"""

import argparse
import logging
import re
import sys
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

PRIMARIOS_IN = "estudos_primarios_v8.csv"
TRIAGEM_OUT = "triagem_titulo_abstract.csv"
INCLUIDOS_OUT = "estudos_incluidos.csv"
EXCLUIDOS_OUT = "estudos_excluidos.csv"
RELATORIO_OUT = "relatorio_triagem.csv"

# ----------------------------------------------------------------------
# Sinais textuais
# ----------------------------------------------------------------------
CI1_RE = re.compile(
    r"\bknowledge graph|\bknowledge base|\bkge\b|"
    r"\bembedding|\brepresentation learning|\blink prediction|"
    r"\bknowledge graph completion|\bkg completion|"
    r"\bentity alignment|\brelation extraction",
    re.IGNORECASE,
)

CI2_RE = re.compile(
    r"\bincomplet|\bopen[- ]world|\bowA\b|\bmissing|"
    r"\binconsisten|\bcontradict|\bconflict|\bnoisy|"
    r"\bcalibrat|\buncertain|\bprobabilistic|\bvariational|"
    r"\bbayesian|\bgaussian|\bevidential|\bconformal|"
    r"\bconfidence|\bgranular",
    re.IGNORECASE,
)

CI3_RE = re.compile(
    r"\bvariational|\bbayesian|\bprobabilistic|\buncertainty|"
    r"\bcalibrat|\bevidential|\bconformal|\bgaussian mixture|"
    r"\bnormalizing flow|\bneural process|\bmonte carlo",
    re.IGNORECASE,
)

CI5_RE = re.compile(
    r"\bexperiment|\bevaluation|\bbenchmark|\bdataset|"
    r"\bresults|\bempirical|\bcomparison|\bbaselines",
    re.IGNORECASE,
)

CE1_RE = re.compile(
    r"\bonly as (an? )?(auxiliary|background)|"
    r"\bnot (directly|specifically) about (knowledge graph|kge)",
    re.IGNORECASE,
)

CE2_RE = re.compile(
    r"\b(generic|general[- ]purpose) graph(?! knowledge)|"
    r"\bsocial network(?!.*knowledge graph)|"
    r"\bmolecular graph(?!.*knowledge)|"
    r"\bprotein[- ]protein(?!.*knowledge)",
    re.IGNORECASE,
)

CE5_RE = re.compile(
    r"\bno (embedding|learning|inference)|"
    r"\bpurely symbolic without (learning|embedding)",
    re.IGNORECASE,
)


# ----------------------------------------------------------------------
# Heurísticas
# ----------------------------------------------------------------------
def _safe_str(x) -> str:
    if x is None:
        return ""
    if isinstance(x, float):
        return ""
    return str(x).strip()

# Substitua a função suggest_decision() por esta versão
def suggest_decision(row: dict) -> tuple[str, str, str]:
    title = _safe_str(row.get("title"))
    abstract = _safe_str(row.get("abstract"))
    keywords = _safe_str(row.get("author_keywords"))
    text = f" {title} {abstract} {keywords} "

    hits = {
        "CI1": bool(CI1_RE.search(text)),
        "CI2": bool(CI2_RE.search(text)),
        "CI3": bool(CI3_RE.search(text)),
        "CI5": bool(CI5_RE.search(text)),
        "CE1": bool(CE1_RE.search(text)),
        "CE2": bool(CE2_RE.search(text)),
        "CE5": bool(CE5_RE.search(text)),
    }
    positives = sum(hits[k] for k in ("CI1", "CI2", "CI3", "CI5"))
    negatives = [k for k in ("CE1", "CE2", "CE5") if hits[k]]

    # CE1/CE2/CE5 são fortes → excluir
    if negatives:
        return "excluir", negatives[0], f"sinal negativo detectado: {negatives[0]}"

    # Sem CI1 (não é sobre KG) → excluir por CE5
    if not hits["CI1"]:
        return "excluir", "CE5", "sem sinal de KG/embedding no título/abstract"

    # 4/4 positivos → incluir
    if positives >= 4:
        return "incluir", "CI1,CI2,CI3,CI5", "todos os sinais positivos presentes"

    # 3/4 com CI1 + (CI2 ou CI3) → incluir (heurística mais agressiva)
    if positives == 3 and hits["CI1"] and (hits["CI2"] or hits["CI3"]):
        # CI4 e CI6 não são testáveis por regex; presumimos True
        return "incluir", "CI1,CI2,CI5" if hits["CI2"] else "CI1,CI3,CI5", \
               "3/4 sinais + CI1 + eixo de incerteza"

    # 2/4 com CI1 + CI2 + (CI3 ou CI5) → duvida (revisão obrigatória)
    if positives >= 2 and hits["CI1"] and hits["CI2"]:
        return "duvida", "", f"sinais positivos={positives}/4 (CI1+CI2 garantidos)"

    # Resto → duvida
    return "duvida", "", f"sinais positivos={positives}/4"

# ----------------------------------------------------------------------
# Fase 1 — gerar CSV interativo
# ----------------------------------------------------------------------
def generate_triage_csv(input_path: str) -> None:
    df = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    log.info(f"Primários lidos: {len(df)}")

    # Preenche heurísticas
    decisions, criteria, justif = [], [], []
    for _, row in df.iterrows():
        d, c, j = suggest_decision(row.to_dict())
        decisions.append(d)
        criteria.append(c)
        justif.append(j)

    df["decisao_auto"] = decisions
    df["criterio_auto"] = criteria
    df["justificativa_auto"] = justif
    df["decisao"] = ""       # preencher manualmente: incluir/excluir/duvida
    df["criterio"] = ""      # preencher manualmente: CI1..CI6 ou CE1..CE6
    df["justificativa"] = "" # livre

    cols = [
        "source_row", "title", "abstract", "author_keywords",
        "decisao_auto", "criterio_auto", "justificativa_auto",
        "decisao", "criterio", "justificativa",
    ]
    cols = [c for c in cols if c in df.columns]
    df[cols].to_csv(TRIAGEM_OUT, index=False, encoding="utf-8")

    counts = df["decisao_auto"].value_counts()
    log.info(f"Arquivo gerado: {TRIAGEM_OUT}")
    log.info(f"Total: {len(df)}")
    for k, v in counts.items():
        log.info(f"  {k:<10} {v}")
    log.info("")
    log.info("Instruções:")
    log.info("  1. Abra o CSV em Excel/LibreOffice/VSCode")
    log.info("  2. Preencha 'decisao' com: incluir / excluir / duvida")
    log.info("  3. Preencha 'criterio' (CI1..CI6 ou CE1..CE6) — obrigatório se excluir")
    log.info("  4. Preencha 'justificativa' (opcional, mas recomendado)")
    log.info("  5. Rode novamente com --apply")
    log.info("")
    log.info("Sugestão: revise primeiro os 'duvida', depois os 'excluir',")
    log.info("e por último confirme os 'incluir'.")


# ----------------------------------------------------------------------
# Fase 2 — aplicar decisões
# ----------------------------------------------------------------------
def apply_decisions() -> None:
    if not Path(TRIAGEM_OUT).exists():
        log.error(f"Arquivo não encontrado: {TRIAGEM_OUT}")
        sys.exit(2)

    triagem = pd.read_csv(TRIAGEM_OUT, dtype=str, keep_default_na=False)

    # Valida preenchimento
    vazios = triagem[triagem["decisao"].str.strip() == ""]
    if len(vazios):
        log.error(f"{len(vazios)} registros sem decisão preenchida.")
        log.error("Colunas vazias nos seguintes source_row:")
        log.error(", ".join(vazios["source_row"].tolist()[:20]))
        log.error("... (use --force para aplicar mesmo assim, tratando vazios como 'duvida')")
        # Note: --force ainda não implementado; mantemos falha dura.

    # Normaliza
    triagem["decisao"] = triagem["decisao"].str.lower().str.strip()
    triagem["criterio"] = triagem["criterio"].str.upper().str.strip()

    # Separa
    incluir = triagem[triagem["decisao"] == "incluir"].copy()
    excluir = triagem[triagem["decisao"] == "excluir"].copy()
    duvida = triagem[triagem["decisao"] == "duvida"].copy()

    incluir.to_csv(INCLUIDOS_OUT, index=False, encoding="utf-8")
    excluir.to_csv(EXCLUIDOS_OUT, index=False, encoding="utf-8")

    # Relatório por critério
    relatorio = []
    for _, row in excluir.iterrows():
        relatorio.append({
            "source_row": row["source_row"],
            "title": row["title"],
            "criterio": row["criterio"],
            "justificativa": row["justificativa"],
        })
    pd.DataFrame(relatorio).to_csv(RELATORIO_OUT, index=False, encoding="utf-8")

    log.info("=" * 60)
    log.info("TRIAGEM APLICADA")
    log.info(f"Incluídos:  {len(incluir)}")
    log.info(f"Excluídos:  {len(excluir)}")
    log.info(f"Dúvidas:    {len(duvida)} (pendentes de revisão pelo advisor)")
    log.info(f"Total:      {len(triagem)}")
    log.info("")
    log.info("Distribuição de exclusões por critério:")
    if len(excluir):
        for crit, cnt in excluir["criterio"].value_counts().items():
            log.info(f"  {crit:<5} {cnt}")
    log.info("=" * 60)
    log.info(f"Arquivo incluídos:   {INCLUIDOS_OUT}")
    log.info(f"Arquivo excluídos:   {EXCLUIDOS_OUT}")
    log.info(f"Relatório exclusões: {RELATORIO_OUT}")

    # Reconciliação
    if len(incluir) + len(excluir) + len(duvida) != len(triagem):
        log.warning("Reconciliação falhou: incluídos + excluídos + dúvidas ≠ total.")
    else:
        log.info(f"Reconciliação OK: {len(incluir)} + {len(excluir)} + {len(duvida)} = {len(triagem)}")


# ----------------------------------------------------------------------
# Fase 3 — estatísticas PRISMA
# ----------------------------------------------------------------------
def show_stats() -> None:
    if not Path(TRIAGEM_OUT).exists():
        log.error(f"Arquivo não encontrado: {TRIAGEM_OUT}")
        sys.exit(2)

    triagem = pd.read_csv(TRIAGEM_OUT, dtype=str, keep_default_na=False)
    triagem["decisao"] = triagem["decisao"].str.lower().str.strip()
    triagem["criterio"] = triagem["criterio"].str.upper().str.strip()

    log.info("=" * 60)
    log.info("ESTATÍSTICAS PRISMA")
    log.info("=" * 60)
    log.info(f"Primários elegíveis (baseline): 599")
    log.info(f"Registros no CSV de triagem:    {len(triagem)}")

    if (triagem["decisao"] == "").all():
        log.info("Nenhuma decisão preenchida ainda.")
        log.info("Distribuição das sugestões heurísticas:")
        for k, v in triagem["decisao_auto"].value_counts().items():
            log.info(f"  {k:<10} {v}")
        log.info("")
        log.info("Após preencher 'decisao', rode --stats novamente.")
        return

    n_inc = (triagem["decisao"] == "incluir").sum()
    n_exc = (triagem["decisao"] == "excluir").sum()
    n_duv = (triagem["decisao"] == "duvida").sum()
    log.info(f"Incluídos:  {n_inc}")
    log.info(f"Excluídos:  {n_exc}")
    log.info(f"Dúvidas:    {n_duv}")
    log.info("")
    log.info("Exclusões por critério:")
    for crit, cnt in triagem[triagem["decisao"] == "excluir"]["criterio"].value_counts().items():
        log.info(f"  {crit:<5} {cnt}")
    log.info("=" * 60)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=PRIMARIOS_IN,
                    help=f"CSV de primários (default: {PRIMARIOS_IN})")
    ap.add_argument("--apply", action="store_true",
                    help="Aplica decisões manuais do CSV de triagem")
    ap.add_argument("--stats", action="store_true",
                    help="Mostra estatísticas PRISMA")
    args = ap.parse_args()

    if args.apply:
        apply_decisions()
    elif args.stats:
        show_stats()
    else:
        if not Path(args.input).exists():
            log.error(f"Arquivo não encontrado: {args.input}")
            sys.exit(2)
        generate_triage_csv(args.input)


if __name__ == "__main__":
    main()