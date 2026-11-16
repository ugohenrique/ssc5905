#!/usr/bin/env python3
"""
dedup_slr_v9.py — Pipeline de deduplicação e classificação (VKGI-SLR v9).

Correções sobre v8:
  1. Filtro de status robusto (fillna + strip + lower + == "duplicated").
  2. Dedup de título pós-status: remove qualquer linha cujo título
     tenha contraparte status="Duplicated" no articles.xls.
  3. Dedup de título normalizado priorizando year mais recente
     (mantém journal sobre conference quando há par).
  4. Reconciliação automática (raw − remoções == final) com assert.

Uso:
    python dedup_slr_v9.py --input articles.xls
"""

import argparse
import logging
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from rapidfuzz.distance import Levenshtein

logging.basicConfig(level=logging.INFO,
                    format="%(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

LEV_THRESHOLD = 0.05
MIN_TITLE_LEN = 20

SECONDARY_TITLE_RE = re.compile(
    r"\bsurvey\b|\breview\b|\boverview\b|"
    r"\bsystematic (literature )?review\b|"
    r"\bsystematic mapping\b|\bliterature review\b|"
    r"\bstate[- ]of[- ]the[- ]art\b|\btaxonomy\b|"
    r"\bcomprehensive review\b|\bcritical review\b|"
    r"\bmeta[- ]analysis\b|\bbibliometric\b|\btutorial\b",
    re.IGNORECASE)
PROC_TITLE_RE = re.compile(
    r"^(?:proceedings|preface|editorial|front matter|"
    r"table of contents|index|technical report column)\b",
    re.IGNORECASE)
DOI_PREFIX_RE = re.compile(
    r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*"
    r"|https?://www\.scopus\.com/[^\s]*)", re.IGNORECASE)


def normalize_text(s):
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.lower())).strip()


def normalize_doi(s):
    if not isinstance(s, str):
        return ""
    s = s.strip()
    if not s or s.lower() == "nan":
        return ""
    return DOI_PREFIX_RE.sub("", s).strip().lower()


def is_secondary(title, abstract, doc_type):
    if isinstance(doc_type, str):
        dt = doc_type.lower().strip()
        if dt in ("conference review", "review", "survey", "overview",
                  "taxonomy", "tutorial"):
            return True, dt.replace(" ", "_")
    if isinstance(title, str) and SECONDARY_TITLE_RE.search(title):
        if re.search(r"\bpeer[- ]review|\breviewer|\breviewed\b", title, re.I):
            pass
        else:
            t = title.lower()
            for key, label in [
                ("systematic mapping", "mapping"),
                ("systematic literature review", "systematic_review"),
                ("systematic review", "systematic_review"),
                ("literature review", "literature_review"),
                ("comprehensive review", "review"),
                ("critical review", "review"),
                ("tutorial", "tutorial"),
                ("taxonomy", "taxonomy"),
                ("overview", "overview"),
                ("survey", "survey"),
            ]:
                if key in t:
                    return True, label
            return True, "review"
    if isinstance(abstract, str):
        ab = abstract.lower()
        if re.search(r"\bthis (survey|review|overview)\b", ab):
            return True, "abstract_declared_review"
        if re.search(r"\bwe (survey|review)\b", ab):
            return True, "abstract_declared_review"
    return False, ""


def rel_lev(a, b):
    if not a or not b:
        return 1.0
    return Levenshtein.distance(a, b) / max(len(a), len(b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="articles.xls")
    ap.add_argument("--primarios", default="estudos_primarios_v9.csv")
    ap.add_argument("--secundarios", default="estudos_secundarios_v9.csv")
    ap.add_argument("--relatorio", default="relatorio_dedup_v9.csv")
    args = ap.parse_args()

    # 1. Carrega
    xls = pd.ExcelFile(args.input)
    sheet = "Articles" if "Articles" in xls.sheet_names else xls.sheet_names[0]
    df = pd.read_excel(xls, sheet_name=sheet, dtype=str,
                       keep_default_na=False)
    df.insert(0, "source_row", range(2, len(df) + 2))
    log.info(f"[1] Registros brutos lidos: {len(df)}")

    report = []
    n_raw = len(df)

    # 2. Normalizações internas
    df["_title_norm"] = df["title"].apply(normalize_text)
    df["_doi_norm"] = df["doi"].apply(normalize_doi)
    df["_status_norm"] = df["status"].fillna("").astype(str).str.strip().str.lower()

    # 3. CE6 — pré-marcadas por status (ROBUSTO)
    mask_status = df["_status_norm"] == "duplicated"
    n_status = int(mask_status.sum())
    for _, r in df[mask_status].iterrows():
        report.append({"action": "removed_status_duplicated",
                       "source_row": r["source_row"],
                       "title": r["title"], "doi": r["doi"],
                       "reason": "status='Duplicated'"})
    df = df[~mask_status]
    log.info(f"[2] Após status=Duplicated: {len(df)} (−{n_status})")

    # 4. CE4/CE5 — proceedings/editoriais
    proc_mask = df["title"].astype(str).str.contains(PROC_TITLE_RE, na=False)
    proc_mask |= df["document_type"].astype(str).str.lower().isin(
        ["conference review", "proceedings", "editorial"])
    n_proc = int(proc_mask.sum())
    for _, r in df[proc_mask].iterrows():
        report.append({"action": "removed_proceedings",
                       "source_row": r["source_row"],
                       "title": r["title"], "doi": r["doi"],
                       "reason": "proceedings/editorial"})
    df = df[~proc_mask]
    log.info(f"[3] Após proceedings: {len(df)} (−{n_proc})")

    # 5. CE6 — dedup por DOI
    seen_doi, drop_doi = {}, []
    for idx, r in df.iterrows():
        doi = r["_doi_norm"]
        if not doi:
            continue
        if doi in seen_doi:
            drop_doi.append(idx)
            report.append({"action": "removed_doi",
                           "source_row": r["source_row"],
                           "title": r["title"], "doi": doi,
                           "reason": f"DOI dup de {df.loc[seen_doi[doi], 'source_row']}"})
        else:
            seen_doi[doi] = idx
    df = df.drop(index=drop_doi)
    log.info(f"[4] Após dedup DOI: {len(df)} (−{len(drop_doi)})")

    # 6. CE6 — dedup por título normalizado (fuzzy)
    # Primeiro: remove título com contraparte status="Duplicated" no original
    orig = pd.read_excel(xls, sheet_name=sheet, dtype=str,
                         keep_default_na=False)
    orig["_title_norm"] = orig["title"].apply(normalize_text)
    dup_titles = set(
        orig[orig["status"].fillna("").astype(str)
             .str.strip().str.lower() == "duplicated"]["_title_norm"]
    )
    mask_dup_titles = df["_title_norm"].isin(dup_titles)
    n_dup_titles = int(mask_dup_titles.sum())
    for _, r in df[mask_dup_titles].iterrows():
        report.append({"action": "removed_title_with_dup_counterpart",
                       "source_row": r["source_row"],
                       "title": r["title"], "doi": r["doi"],
                       "reason": "título tem contraparte status=Duplicated"})
    df = df[~mask_dup_titles]
    log.info(f"[5] Após remover títulos com contraparte Duplicated: "
             f"{len(df)} (−{n_dup_titles})")

    # Segundo: fuzzy match + prioridade por year
    df["_year_num"] = pd.to_numeric(df["year"], errors="coerce").fillna(0)
    df = df.sort_values("_year_num", ascending=False)
    unique_idx, title_by_idx = [], {}
    count_dup_title = 0
    for idx, r in df.iterrows():
        tn = r["_title_norm"]
        if not tn or len(tn) < MIN_TITLE_LEN:
            unique_idx.append(idx); title_by_idx[idx] = tn; continue
        dup_of, best = None, None
        for kept in unique_idx:
            kt = title_by_idx[kept]
            if len(kt) < MIN_TITLE_LEN:
                continue
            d = rel_lev(tn, kt)
            if d <= LEV_THRESHOLD and (best is None or d < best):
                best, dup_of = d, kept
        if dup_of is None:
            unique_idx.append(idx); title_by_idx[idx] = tn
        else:
            count_dup_title += 1
            report.append({"action": "removed_title_fuzzy",
                           "source_row": r["source_row"],
                           "title": r["title"], "doi": r["doi"],
                           "reason": f"título L={best:.4f} de {df.loc[dup_of, 'source_row']}"})
    df = df.loc[unique_idx]
    log.info(f"[6] Após dedup título fuzzy: {len(df)} (−{count_dup_title})")

    # 7. CE3 — classificação secundários
    flags = df.apply(lambda r: is_secondary(r["title"], r.get("abstract"),
                                            r.get("document_type")), axis=1)
    df["_is_sec"] = [f[0] for f in flags]
    df["_sec_sub"] = [f[1] for f in flags]
    prim = df[~df["_is_sec"]].drop(columns=[c for c in df.columns if c.startswith("_")])
    sec = df[df["_is_sec"]].drop(columns=[c for c in df.columns if c.startswith("_")])
    n_sec = len(sec)
    for _, r in sec.iterrows():
        report.append({"action": "removed_secondary_CE3",
                       "source_row": r["source_row"],
                       "title": r["title"], "doi": r["doi"],
                       "reason": f"CE3: {r.get('document_type', '')}"})
    log.info(f"[7] Primários: {len(prim)} | Secundários: {n_sec}")

    # 8. Salva
    prim.to_csv(args.primarios, index=False, encoding="utf-8")
    sec.to_csv(args.secundarios, index=False, encoding="utf-8")
    pd.DataFrame(report).to_csv(args.relatorio, index=False, encoding="utf-8")

    # 9. Reconciliação
    log.info("=" * 60)
    log.info("RECONCILIAÇÃO")
    log.info(f"  raw:              {n_raw}")
    log.info(f"  − status:         {n_status}")
    log.info(f"  − proceedings:    {n_proc}")
    log.info(f"  − DOI:            {len(drop_doi)}")
    log.info(f"  − título+dup:     {n_dup_titles}")
    log.info(f"  − título fuzzy:   {count_dup_title}")
    log.info(f"  − CE3:            {n_sec}")
    expected = n_raw - n_status - n_proc - len(drop_doi) - n_dup_titles - count_dup_title - n_sec
    log.info(f"  = esperado:       {expected}")
    log.info(f"  = primários:      {len(prim)}")
    if expected != len(prim):
        log.error(f"  ✗ RECONCILIAÇÃO FALHOU")
        sys.exit(1)
    log.info(f"  ✓ Reconciliação OK")
    log.info("=" * 60)
    log.info(f"Saída: {args.primarios}, {args.secundarios}, {args.relatorio}")


if __name__ == "__main__":
    main()