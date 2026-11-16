#!/usr/bin/env python3
"""apply_duvida.py (v2) — Mescla decisões da revisão em blocos no CSV principal."""
import pandas as pd
import sys

df = pd.read_csv("triagem_titulo_abstract.csv", dtype=str, keep_default_na=False)
rev = pd.read_csv("revisao_duvida_em_blocos.csv", dtype=str, keep_default_na=False)

# Verifica se há decisões preenchidas
preenchidas = rev["decisao_final"].astype(str).str.strip().ne("").sum()
if preenchidas == 0:
    print(f" Nenhuma decisão preenchida em 'decisao_final'.")
    print(f"  Total de linhas a revisar: {len(rev)}")
    print(f"  Abra 'revisao_duvida_em_blocos.csv' e preencha 'decisao_final'")
    print(f"  com 'incluir', 'excluir' ou 'duvida'.")
    sys.exit(1)

# Mapeia source_row → decisão final
decisoes = {}
for _, r in rev.iterrows():
    sr = str(r["source_row"]).strip()
    dec = r.get("decisao_final", "").strip().lower()
    crit = r.get("criterio_final", "").strip().upper()
    if dec:
        decisoes[sr] = (dec, crit, r.get("justificativa", ""))

# Aplica
n_aplicados = 0
for idx, r in df.iterrows():
    sr = str(r["source_row"]).strip()
    if sr in decisoes:
        dec, crit, just = decisoes[sr]
        df.at[idx, "decisao"] = dec
        df.at[idx, "criterio"] = crit
        df.at[idx, "justificativa"] = just
        n_aplicados += 1

df.to_csv("triagem_titulo_abstract.csv", index=False, encoding="utf-8")
print(f"Decisões aplicadas: {n_aplicados} / {len(rev)}")