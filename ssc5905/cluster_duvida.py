#!/usr/bin/env python3
"""
cluster_duvida.py (v2) — Agrupa os 'duvida' em blocos temáticos
para revisão em lote.

Correções v2:
  - Regex independentes (OR, não AND) em cada bloco.
  - Blocos de fallback granulares por keyword individual.
  - Ordem dos blocos: específicos primeiro, genéricos depois.
  - Log de debug: quantos registros cada bloco captura.
"""

import re
import pandas as pd

BLOCOS = [
    # (nome, padrões a buscar — basta 1 match, decisão, critério)
    # --- Grupos de inclusão (escopo) ---
    ("KGE + incerteza/calibração",
     r"\b(uncertain|probabilistic|variational|bayesian|gaussian|"
     r"calibrat|inconsisten|contradict|evidential|conformal|"
     r"confidence|noisy|error.?aware)\b",
     "incluir", "CI1,CI2,CI3"),

    ("KGE + incompletude/OWA",
     r"\b(incomplet|open.?world|owa|missing|few.?shot|sparse)\b",
     "incluir", "CI1,CI2,CI5"),

    ("Ontology embedding / Description Logic",
     r"\b(ontology embedding|description logic|dl.?lite|el\+\+|el\b|"
     r"alc\b|owl|box embedding|cone embedding|geometric embedding)\b",
     "incluir", "CI1,CI2"),

    ("Neuro-symbolic / logic + learning",
     r"\b(neuro.?symbolic|neural.?symbolic|fuzzy logic|"
     r"rule learning|logic programming|markov logic|"
     r"answer set programming|abductive|deductive)\b",
     "incluir", "CI1,CI2"),

    ("Query embedding / logical query answering",
     r"\b(query embedding|logical query|complex query|multi.?hop|"
     r"first.?order logic|fol query|dag query)\b",
     "incluir", "CI1,CI2"),

    ("KGE / knowledge graph embedding",
     r"\b(knowledge graph embedding|kge|graph embedding|"
     r"embedding model|representation learning)\b",
     "incluir", "CI1,CI2"),

    # --- Grupos de exclusão (fora do escopo) ---
    ("Recommendation / user modeling (fora do escopo)",
     r"\b(recommend|collaborative filter|user model|item recommend|"
     r"session.?based|cold.?start)\b",
     "excluir", "CE5"),

    ("Vision / speech / NLP (fora do escopo)",
     r"\b(image|video|speech|audio|sentiment|machine translation|"
     r"text classif|aspect.?based|poetry|music|playlist)\b",
     "excluir", "CE5"),

    ("Finance / stock / risk (fora do escopo)",
     r"\b(stock|trading|portfolio|financial risk|credit scor|"
     r"fraud|misinformation)\b",
     "excluir", "CE5"),

    ("Healthcare / clinical (KG só auxiliar)",
     r"\b(clinical|patient|diagnosis|ehr|electronic health|"
     r"medical cod|disease|drug.?(target|repurpos)|symptom)\b",
     "excluir", "CE1"),

    ("IoT / smart city / cyber (KG só auxiliar)",
     r"\b(iot|smart city|cyber|intrusion|network security|"
     r"fog|edge comput|5g|6g|wireless)\b",
     "excluir", "CE1"),

    ("Education / learning analytics (KG só auxiliar)",
     r"\b(student|course|education|learning path|tutor|"
     r"curriculum|grading)\b",
     "excluir", "CE1"),

    # --- Fallbacks granulares ---
    ("Fallback: KG mencionado (potencial incluir)",
     r"\b(knowledge graph|knowledge base|kg)\b",
     "duvida", ""),

    ("Fallback: ML/deep learning sem KG",
     r"\b(deep learning|neural network|transformer|bert|"
     r"attention|gnn|graph neural network)\b",
     "duvida", ""),

    ("Fallback: incerteza sem KG",
     r"\b(uncertain|probabilistic|variational|bayesian|"
     r"calibrat|inconsisten)\b",
     "duvida", ""),

    # --- Último recurso ---
    ("Fallback: sem match",
     r".*",
     "duvida", ""),
]


def classify(title, keywords):
    text = f"{title} {keywords}".lower()
    for nome, pat, dec, crit in BLOCOS:
        if re.search(pat, text, re.IGNORECASE):
            return nome, dec, crit
    return "Fallback: sem match", "duvida", ""


def main():
    df = pd.read_csv("triagem_titulo_abstract.csv", dtype=str,
                     keep_default_na=False)
    duv = df[df["decisao_auto"] == "duvida"].copy()

    resultados = []
    for _, r in duv.iterrows():
        bloco, dec, crit = classify(r["title"], r.get("author_keywords", ""))
        resultados.append({
            "source_row": r["source_row"],
            "title": r["title"],
            "abstract_inicio": (r.get("abstract", "") or "")[:200],
            "author_keywords": r.get("author_keywords", ""),
            "bloco": bloco,
            "decisao_sugerida": dec,
            "criterio_sugerido": crit,
            "decisao_final": "",
            "criterio_final": "",
            "justificativa": "",
        })
    out = pd.DataFrame(resultados)
    out.to_csv("revisao_duvida_em_blocos.csv", index=False, encoding="utf-8")

    print(f"Total 'duvida': {len(out)}")
    print()
    print("Distribuição por bloco:")
    for bloco, cnt in out["bloco"].value_counts().items():
        sug = out[out["bloco"] == bloco]["decisao_sugerida"].iloc[0]
        print(f"  [{sug:<8}] {bloco:<50} {cnt:>3}")
    print()
    print("Arquivo gerado: revisao_duvida_em_blocos.csv")
    print("Instruções:")
    print("  1. Filtre por 'bloco' no Excel/LibreOffice")
    print("  2. Para cada bloco, se 'decisao_sugerida' for coerente,")
    print("     copie para 'decisao_final' e 'criterio_final'.")
    print("  3. Ajuste caso a caso os que estiverem no bloco errado.")
    print("  4. Salve e rode: python apply_duvida.py")


if __name__ == "__main__":
    main()