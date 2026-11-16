#!/usr/bin/env python3
"""
dedup_slr_v8.py — Pipeline completo v8 para o protocolo VKGI-SLR.

Lê DIRETAMENTE o arquivo original articles.xls (aba "Articles") e produz
três CSV:
  - estudos_primarios_v8.csv     (primários para triagem)
  - estudos_secundarios_v8.csv   (CE3: surveys/reviews/mapeamentos)
  - relatorio_dedup_v8.csv       (auditoria completa)

Correções sobre v7:
  1. Detecta automaticamente a aba "Articles" (ou a primeira aba com
     coluna 'title').
  2. Gera source_row a partir da linha física do Excel (cabeçalho = 1,
     primeiro estudo = 2).
  3. Normaliza DOI com case-insensitive + remoção de prefixos Scopus
     (https://www.scopus.com/...) e doi.org.
  4. Classifica CE3 (secundários) por document_type + title + abstract.
  5. Classifica CE4/CE5 (proceedings) por document_type='Conference review'
     ou title começando com "Proceedings"/"Preface"/"Editorial".
  6. Remove duplicatas pré-marcadas por status='Duplicated'.
  7. Remove duplicatas por DOI e por título (Levenshtein).
  8. Saída final auditável com contagem por ação.

Uso:
    python dedup_slr_v8.py --input articles.xls
"""

import argparse
import logging
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from rapidfuzz.distance import Levenshtein

# ----------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------
LEVENSHTEIN_THRESHOLD = 0.05
MIN_TITLE_LEN = 20

# Padrões para detectar estudos SECUNDÁRIOS (CE3)
SECONDARY_TITLE_RE = re.compile(
    r"\bsurvey\b|\breview\b|\boverview\b|"
    r"\bsystematic (literature )?review\b|"
    r"\bsystematic mapping\b|"
    r"\bliterature review\b|"
    r"\bstate[- ]of[- ]the[- ]art\b|"
    r"\btaxonomy\b|\bcomprehensive review\b|\bcritical review\b|"
    r"\bmeta[- ]analysis\b|\bbibliometric\b|\btutorial\b|"
    r"\breview of\b|\bsurvey on\b|\bsurvey of\b",
    re.IGNORECASE,
)

# Padrões para detectar PROCEEDINGS / editoriais (CE4/CE5)
PROC_TITLE_RE = re.compile(
    r"^(?:proceedings|preface|editorial|front matter|"
    r"table of contents|index|technical report column)\b",
    re.IGNORECASE,
)

# DOI: prefixos a remover + normalização
DOI_PREFIX_RE = re.compile(
    r"^(?:"
    r"https?://(?:dx\.)?doi\.org/"
    r"|doi:\s*"
    r"|https?://www\.scopus\.com/pages/publications/\d+\??[^/]*"
    r"|https?://www\.scopus\.com/[^\s]*"
    r")",
    re.IGNORECASE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Funções auxiliares
# ----------------------------------------------------------------------
def normalize_text(s) -> str:
    """Minúsculas, remove acentos, pontuação e espaços múltiplos."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_doi(s) -> str:
    """Remove prefixos e normaliza DOI para comparação (lowercase)."""
    if not isinstance(s, str):
        return ""
    s = s.strip()
    if not s or s.lower() == "nan":
        return ""
    s = DOI_PREFIX_RE.sub("", s)
    return s.strip().lower()


def first_author_surname(authors) -> str:
    """Extrai o sobrenome do primeiro autor (heurística)."""
    if not isinstance(authors, str) or not authors.strip():
        return ""
    first = authors.split(" and ")[0].split(",")[0].strip()
    parts = [p for p in re.split(r"[\s,]+", first) if p]
    return normalize_text(parts[-1]) if parts else ""


def is_secondary(title, abstract, doc_type) -> tuple[bool, str]:
    """
    Detecta estudo secundário (CE3).
    Retorna (é_secundário, subtipo).
    """
    # 1. document_type explícito
    if isinstance(doc_type, str):
        dt = doc_type.lower().strip()
        if dt in ("conference review", "review", "survey", "book chapter"):
            # "Book chapter" NÃO é secundário por si só — ignorar
            if dt != "book chapter":
                return True, dt.replace(" ", "_")

    # 2. Título com padrão de survey/review/mapping
    if isinstance(title, str) and SECONDARY_TITLE_RE.search(title):
        # Falsos positivos: "peer review", "reviewer", "reviewed"
        if re.search(r"\bpeer[- ]review", title, re.I):
            pass  # não é secundário
        elif re.search(r"\breviewer|\breviewed\b", title, re.I):
            pass
        else:
            t = title.lower()
            if "systematic mapping" in t:
                return True, "mapping"
            if "systematic literature review" in t or "systematic review" in t:
                return True, "systematic_review"
            if "literature review" in t:
                return True, "literature_review"
            if "comprehensive review" in t or "critical review" in t:
                return True, "review"
            if "tutorial" in t:
                return True, "tutorial"
            if "taxonomy" in t:
                return True, "taxonomy"
            if "overview" in t:
                return True, "overview"
            if "survey" in t:
                return True, "survey"
            return True, "review"

    # 3. Abstract com "this survey", "this review", "we survey", etc.
    if isinstance(abstract, str):
        ab = abstract.lower()
        if re.search(r"\bthis (survey|review|overview)\b", ab):
            return True, "abstract_declared_review"
        if re.search(r"\bwe (survey|review)\b", ab):
            return True, "abstract_declared_review"

    return False, ""


def is_proceedings(title, doc_type) -> bool:
    """CE4/CE5: proceedings, preface, editorial, technical report column."""
    if isinstance(title, str) and PROC_TITLE_RE.search(title.strip()):
        return True
    if isinstance(doc_type, str):
        dt = doc_type.lower()
        if dt in ("conference review", "proceedings", "editorial"):
            return True
    return False


def relative_levenshtein(a: str, b: str) -> float:
    if not a or not b:
        return 1.0
    return Levenshtein.distance(a, b) / max(len(a), len(b))


# ----------------------------------------------------------------------
# Leitura robusta do articles.xls
# ----------------------------------------------------------------------
def load_articles_xls(path: str) -> pd.DataFrame:
    """
    Lê o articles.xls, detecta automaticamente a aba correta (que tenha
    a coluna 'title') e retorna o DataFrame com dtype=str.
    """
    log.info(f"Lendo {path}...")
    xls = pd.ExcelFile(path)
    log.info(f"Abas encontradas: {xls.sheet_names}")

    # Tenta primeiro a aba "Articles", depois qualquer aba com 'title'
    target_sheet = None
    if "Articles" in xls.sheet_names:
        target_sheet = "Articles"
    else:
        for sh in xls.sheet_names:
            df_test = pd.read_excel(xls, sheet_name=sh, dtype=str, nrows=0)
            cols = {c.strip().lower() for c in df_test.columns}
            if "title" in cols:
                target_sheet = sh
                break

    if target_sheet is None:
        log.error(f"Nenhuma aba com coluna 'title' encontrada em {path}")
        sys.exit(2)

    log.info(f"Aba selecionada: '{target_sheet}'")
    df = pd.read_excel(xls, sheet_name=target_sheet, dtype=str, header=0)

    # Gera source_row: linha física do Excel (cabeçalho = 1, primeiro estudo = 2)
    df = df.reset_index(drop=True)
    df.insert(0, "source_row", range(2, len(df) + 2))

    log.info(f"Registros lidos: {len(df)}")
    log.info(f"source_row: min={df['source_row'].min()} max={df['source_row'].max()}")
    return df


# ----------------------------------------------------------------------
# Pipeline v8
# ----------------------------------------------------------------------
def deduplicate_and_classify(df: pd.DataFrame):
    df = df.copy()

    # Garante colunas esperadas
    for col in ("title", "author", "doi", "status", "document_type", "abstract"):
        if col not in df.columns:
            df[col] = ""

    # Normalizações internas (prefixo _ para limpeza posterior)
    df["_title_norm"] = df["title"].apply(normalize_text)
    df["_doi_norm"] = df["doi"].apply(normalize_doi)
    df["_surname"] = df["author"].apply(first_author_surname)

    # Classificações estáticas
    df["_is_secondary"] = df.apply(
        lambda r: is_secondary(r.get("title"), r.get("abstract"), r.get("document_type"))[0],
        axis=1,
    )
    df["_secondary_subtype"] = df.apply(
        lambda r: is_secondary(r.get("title"), r.get("abstract"), r.get("document_type"))[1],
        axis=1,
    )
    df["_is_proc"] = df.apply(
        lambda r: is_proceedings(r.get("title"), r.get("document_type")),
        axis=1,
    )

    report = []

    # ------------------------------------------------------------------
    # PASSO 1 — Duplicatas pré-marcadas (status='Duplicated')
    # ------------------------------------------------------------------
    mask_dup = df["status"].astype(str).str.contains("duplicat", case=False, na=False)
    count_dup = int(mask_dup.sum())
    for _, row in df[mask_dup].iterrows():
        report.append({
            "action": "removed_pre_marked_duplicate",
            "source_row": row["source_row"],
            "title": row.get("title", ""),
            "doi": row.get("doi", ""),
            "reason": "CE6: status='Duplicated'",
        })
    df = df[~mask_dup]
    log.info(f"Após remover duplicatas pré-marcadas (status): {len(df)} (removidos: {count_dup})")

    # ------------------------------------------------------------------
    # PASSO 2 — Proceedings / editoriais (CE4/CE5)
    # ------------------------------------------------------------------
    proc = df[df["_is_proc"]]
    count_proc = len(proc)
    for _, row in proc.iterrows():
        report.append({
            "action": "removed_proceedings",
            "source_row": row["source_row"],
            "title": row.get("title", ""),
            "doi": row.get("doi", ""),
            "reason": "CE4/CE5: proceedings/editorial/technical report",
        })
    df = df[~df["_is_proc"]]
    log.info(f"Após remover proceedings/editoriais: {len(df)} (removidos: {count_proc})")

    # ------------------------------------------------------------------
    # PASSO 3 — Deduplicação por DOI (CE6)
    # ------------------------------------------------------------------
    seen_doi = {}
    drop_doi_idx = []
    for idx, row in df.iterrows():
        doi = row["_doi_norm"]
        if not doi:
            continue
        if doi in seen_doi:
            drop_doi_idx.append(idx)
            report.append({
                "action": "removed_duplicate_doi",
                "source_row": row["source_row"],
                "title": row.get("title", ""),
                "doi": doi,
                "reason": f"CE6: DOI duplicado (mantido source_row "
                          f"{df.loc[seen_doi[doi], 'source_row']})",
            })
        else:
            seen_doi[doi] = idx
    df = df.drop(index=drop_doi_idx)
    log.info(f"Após deduplicação por DOI: {len(df)} (removidos: {len(drop_doi_idx)})")

    # ------------------------------------------------------------------
    # PASSO 4 — Deduplicação por título (CE6)
    # ------------------------------------------------------------------
    unique_indices = []
    title_by_idx = {}
    count_title_dup = 0

    for idx, row in df.iterrows():
        title_n = row["_title_norm"]
        if not title_n or len(title_n) < MIN_TITLE_LEN:
            unique_indices.append(idx)
            title_by_idx[idx] = title_n
            continue

        surname = row["_surname"]
        duplicate_of = None
        best_distance = None

        for kept_idx in unique_indices:
            kept_title = title_by_idx[kept_idx]
            if len(kept_title) < MIN_TITLE_LEN:
                continue
            d = relative_levenshtein(title_n, kept_title)

            # Match forte: d <= 0.05 (sem checar autor)
            if d <= LEVENSHTEIN_THRESHOLD:
                if best_distance is None or d < best_distance:
                    best_distance = d
                    duplicate_of = kept_idx
            # Match desempatado: 0.05 < d <= 0.10 AND mesmo sobrenome
            elif d <= 2 * LEVENSHTEIN_THRESHOLD:
                if surname and surname == df.loc[kept_idx, "_surname"]:
                    if best_distance is None or d < best_distance:
                        best_distance = d
                        duplicate_of = kept_idx

        if duplicate_of is None:
            unique_indices.append(idx)
            title_by_idx[idx] = title_n
        else:
            count_title_dup += 1
            report.append({
                "action": "removed_duplicate_title",
                "source_row": row["source_row"],
                "title": row.get("title", ""),
                "doi": row.get("doi", ""),
                "reason": f"CE6: título similar (Levenshtein={best_distance:.4f}) "
                          f"ao source_row {df.loc[duplicate_of, 'source_row']}",
            })

    df = df.loc[unique_indices]
    log.info(f"Após deduplicação por título: {len(df)} (removidos: {count_title_dup})")

    # ------------------------------------------------------------------
    # PASSO 5 — Separação CE3 (secundários) vs primários
    # ------------------------------------------------------------------
    secundarios = df[df["_is_secondary"]].copy()
    primarios = df[~df["_is_secondary"]].copy()

    for _, row in secundarios.iterrows():
        report.append({
            "action": "removed_secondary_CE3",
            "source_row": row["source_row"],
            "title": row.get("title", ""),
            "doi": row.get("doi", ""),
            "reason": f"CE3: {row['_secondary_subtype']}",
        })

    log.info(f"Secundários excluídos (CE3): {len(secundarios)}")
    log.info(f"Primários para triagem: {len(primarios)}")

    # ------------------------------------------------------------------
    # Limpeza de colunas auxiliares
    # ------------------------------------------------------------------
    aux_cols = [c for c in primarios.columns if c.startswith("_")]
    primarios = primarios.drop(columns=aux_cols)
    aux_cols = [c for c in secundarios.columns if c.startswith("_")]
    secundarios = secundarios.drop(columns=aux_cols)

    return primarios, secundarios, pd.DataFrame(report)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="articles.xls (original)")
    parser.add_argument("--primarios", default="estudos_primarios_v8.csv")
    parser.add_argument("--secundarios", default="estudos_secundarios_v8.csv")
    parser.add_argument("--relatorio", default="relatorio_dedup_v8.csv")
    args = parser.parse_args()

    df = load_articles_xls(args.input)
    n_raw = len(df)

    primarios, secundarios, report = deduplicate_and_classify(df)

    primarios.to_csv(args.primarios, index=False, encoding="utf-8")
    secundarios.to_csv(args.secundarios, index=False, encoding="utf-8")
    report.to_csv(args.relatorio, index=False, encoding="utf-8")

    log.info("=" * 60)
    log.info("RESUMO FINAL v8")
    log.info(f"Registros brutos lidos (articles.xls): {n_raw}")
    log.info(f"Primários para triagem:                {len(primarios)}")
    log.info(f"Secundários excluídos (CE3):           {len(secundarios)}")
    log.info(f"Total de remoções no relatório:        {len(report)}")

    log.info("\nDetalhamento das ações:")
    if len(report):
        for action, count in report["action"].value_counts().items():
            log.info(f"  - {action:<35} {count}")

    # Reconciliação
    expected = (
        n_raw
        - int((report["action"] == "removed_pre_marked_duplicate").sum())
        - int((report["action"] == "removed_proceedings").sum())
        - int((report["action"] == "removed_duplicate_doi").sum())
        - int((report["action"] == "removed_duplicate_title").sum())
        - int((report["action"] == "removed_secondary_CE3").sum())
    )
    if expected != len(primarios):
        log.warning(
            f"Reconciliação: bruto({n_raw}) - remoções({len(report)}) = "
            f"{expected}, mas o CSV de primários tem {len(primarios)}. "
            f"Verifique sobreposições."
        )
    else:
        log.info(f"Reconciliação OK: {n_raw} - {len(report)} = {len(primarios)}")

    log.info("=" * 60)
    log.info(f"Arquivo primários:    {args.primarios}")
    log.info(f"Arquivo secundários:  {args.secundarios}")
    log.info(f"Relatório:            {args.relatorio}")


if __name__ == "__main__":
    main()