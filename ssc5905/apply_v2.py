#!/usr/bin/env python3
"""
apply_v2.py — Aplica as decisões do auditoria_ce3.csv:
  - source_row com decisao='primario' → move de secundarios para primarios
  - source_row com decisao='secundario' → mantém em secundarios
  - registra no relatório

Uso:
    python apply_v2.py
"""
import pandas as pd

AUDITORIA = "auditoria_ce3.csv"
PRIMARIOS = "estudos_primarios_v8.csv"
SECUNDARIOS = "estudos_secundarios_v8.csv"
RELATORIO = "relatorio_dedup_v8.csv"

# Carrega
audit = pd.read_csv(AUDITORIA, dtype=str, keep_default_na=False)
prim = pd.read_csv(PRIMARIOS, dtype=str, keep_default_na=False)
sec = pd.read_csv(SECUNDARIOS, dtype=str, keep_default_na=False)
rep = pd.read_csv(RELATORIO, dtype=str, keep_default_na=False)

# Normaliza source_row como string
audit["source_row"] = audit["source_row"].astype(str).str.strip()
prim["source_row"] = prim["source_row"].astype(str).str.strip()
sec["source_row"] = sec["source_row"].astype(str).str.strip()

# Filtra os que devem voltar para primários
to_primary = audit[audit["decisao"].str.lower().str.strip() == "primario"]
to_primary_rows = set(to_primary["source_row"])
print(f"Auditoria: {len(audit)} linhas")
print(f"  → secundario: {(audit['decisao'].str.lower().str.strip() == 'secundario').sum()}")
print(f"  → primario:   {len(to_primary_rows)}")

# Move
moved = sec[sec["source_row"].isin(to_primary_rows)].copy()
sec_remaining = sec[~sec["source_row"].isin(to_primary_rows)].copy()
prim_updated = pd.concat([prim, moved], ignore_index=True)

# Salva
prim_updated.to_csv(PRIMARIOS, index=False, encoding="utf-8")
sec_remaining.to_csv(SECUNDARIOS, index=False, encoding="utf-8")

# Atualiza relatório: muda ação dos reclassificados
reclassified = []
for _, row in moved.iterrows():
    reclassified.append({
        "action": "reclassified_CE3_to_primary",
        "source_row": row["source_row"],
        "title": row.get("title", ""),
        "doi": row.get("doi", ""),
        "reason": "Auditoria manual: contribuição técnica original confirmada",
    })
# Remove linhas antigas de removed_secondary_CE3 dos movidos
rep = rep[~((rep["action"] == "removed_secondary_CE3") &
            (rep["source_row"].isin(to_primary_rows)))]
rep = pd.concat([rep, pd.DataFrame(reclassified)], ignore_index=True)
rep.to_csv(RELATORIO, index=False, encoding="utf-8")

print(f"\nMovidos: {len(moved)} secundários → primários")
print(f"Primários agora: {len(prim_updated)}")
print(f"Secundários agora: {len(sec_remaining)}")
print(f"Relatório atualizado: {RELATORIO}")