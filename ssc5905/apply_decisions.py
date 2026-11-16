#!/usr/bin/env python3
"""Aplica as decisões recomendadas aos 35 casos 'revisar'."""
import pandas as pd

SECUNDARIOS = {
    123, 124, 170, 201, 208, 221, 267, 273, 276, 284, 286, 318, 323, 324,
    325, 343, 351, 364, 367, 374, 385, 406, 407, 408, 416, 424, 441, 493,
    530, 540, 705,
}
PRIMARIOS = {242, 383, 534, 580}

df = pd.read_csv("auditoria_ce3_preenchida.csv", dtype=str, keep_default_na=False)
for i, row in df.iterrows():
    try:
        sr = int(float(row["source_row"]))
    except (ValueError, TypeError):
        continue
    if sr in SECUNDARIOS:
        df.at[i, "decisao"] = "secundario"
        df.at[i, "motivo_auto"] = "revisao_manual: survey/review explicito"
    elif sr in PRIMARIOS:
        df.at[i, "decisao"] = "primario"
        df.at[i, "motivo_auto"] = "revisao_manual: contribuicao tecnica original"

df.to_csv("auditoria_ce3_preenchida.csv", index=False, encoding="utf-8")
print(df["decisao"].value_counts())