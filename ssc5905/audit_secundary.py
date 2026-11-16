#!/usr/bin/env python3
"""
audit_secondary.py — Auditoria manual dos estudos secundários (CE3).

Gera um CSV interativo para revisão humana dos 84 secundários.
Você preenche a coluna 'decisao' com 'primario' ou 'secundario'
e roda o script de novo para aplicar a reclassificação.

Uso:
    python audit_secondary.py --secundarios estudos_secundarios_v8.csv \
                              --primarios estudos_primarios_v8.csv \
                              --auditoria auditoria_ce3.csv
"""
import argparse
import pandas as pd
import re


def first_sentence(s, max_len=300):
    if not isinstance(s, str):
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"^(.{20,%d}?[\.\?!])\s" % max_len, s)
    return m.group(1) if m else s[:max_len]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secundarios", default="estudos_secundarios_v8.csv")
    ap.add_argument("--primarios", default="estudos_primarios_v8.csv")
    ap.add_argument("--auditoria", default="auditoria_ce3.csv")
    ap.add_argument("--apply", action="store_true",
                    help="Aplica as decisões já preenchidas no CSV de auditoria")
    args = ap.parse_args()

    if args.apply:
        # Aplica reclassificações
        audit = pd.read_csv(args.auditoria, dtype=str)
        to_primary = audit[audit["decisao"].str.lower() == "primario"]
        sec = pd.read_csv(args.secundarios, dtype=str)
        prim = pd.read_csv(args.primarios, dtype=str)
        moved = sec[sec["source_row"].isin(to_primary["source_row"])]
        sec = sec[~sec["source_row"].isin(to_primary["source_row"])]
        prim = pd.concat([prim, moved], ignore_index=True)
        prim.to_csv(args.primarios, index=False, encoding="utf-8")
        sec.to_csv(args.secundarios, index=False, encoding="utf-8")
        print(f"Reclassificados: {len(moved)} secundários → primários")
        print(f"Primários agora: {len(prim)}")
        print(f"Secundários agora: {len(sec)}")
        return

    # Gera o CSV de auditoria (primeira vez)
    sec = pd.read_csv(args.secundarios, dtype=str)
    sec["abstract_inicio"] = sec["abstract"].apply(first_sentence)
    sec["decisao"] = ""  # preencher: 'primario' ou 'secundario'
    cols = ["source_row", "title", "document_type", "abstract_inicio",
            "author_keywords", "decisao"]
    cols = [c for c in cols if c in sec.columns]
    sec[cols].to_csv(args.auditoria, index=False, encoding="utf-8")
    print(f"Auditoria gerada: {args.auditoria}")
    print(f"Total a revisar: {len(sec)}")
    print("\nInstruções:")
    print("  1. Abra o CSV em um editor (Excel, LibreOffice, VSCode)")
    print("  2. Preencha a coluna 'decisao' com 'primario' ou 'secundario'")
    print("     - 'primario'    = tem contribuição técnica original (novo método)")
    print("     - 'secundario'  = é survey/review/mapeamento (revisão da literatura)")
    print("  3. Salve e rode novamente com --apply")


if __name__ == "__main__":
    main()