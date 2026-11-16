#!/usr/bin/env python3
"""
renomear_pdfs.py
Renomeia PDFs com base no título do paper extraído do próprio PDF.

Uso:
    python renomear_pdfs.py /caminho/da/pasta
    python renomear_pdfs.py /caminho/da/pasta --dry-run   # simula sem alterar
"""

import sys
import re
import argparse
from pathlib import Path
from datetime import datetime

try:
    from pypdf import PdfReader
except ImportError:
    print("Instale a dependência: pip install pypdf")
    sys.exit(1)


# Caracteres proibidos em nomes de arquivo (Windows/Linux/macOS)
INVALID_CHARS = r'[<>:"/\\|?*\x00-\x1F]'
MAX_LEN = 180  # limite de tamanho do nome


def sanitize(name: str) -> str:
    """Remove caracteres inválidos e normaliza espaços."""
    name = re.sub(INVALID_CHARS, "", name)
    name = re.sub(r"\s+", " ", name).strip()
    # Remove pontos finais (Windows não aceita)
    name = name.rstrip(".")
    if len(name) > MAX_LEN:
        name = name[:MAX_LEN].rstrip()
    return name


def extrair_titulo_pdf(pdf_path: Path) -> str | None:
    """Tenta extrair o título dos metadados ou da primeira página."""
    try:
        reader = PdfReader(str(pdf_path))
    except Exception as e:
        print(f"  [erro] Não foi possível abrir {pdf_path.name}: {e}")
        return None

    # 1) Tenta metadados
    meta = reader.metadata or {}
    titulo = (meta.get("/Title") or "").strip()
    if titulo and len(titulo) > 5 and not titulo.lower().startswith("untitled"):
        return titulo

    # 2) Fallback: primeira página (heurística)
    if len(reader.pages) > 0:
        try:
            texto = reader.pages[0].extract_text() or ""
            linhas = [l.strip() for l in texto.splitlines() if l.strip()]
            # Junta as primeiras linhas com tamanho razoável até encontrar
            # uma "linha de título" (geralmente as 1-3 primeiras linhas)
            candidatos = [l for l in linhas[:5] if 10 < len(l) < 250]
            if candidatos:
                return candidatos[0]
        except Exception:
            pass
    return None


def renomear_pdfs(pasta: Path, dry_run: bool = False) -> None:
    pdfs = sorted(pasta.rglob("*.pdf"))
    if not pdfs:
        print(f"Nenhum PDF encontrado em {pasta}")
        return

    print(f"Encontrados {len(pdfs)} PDFs em {pasta}\n")
    renomeados = 0
    falhas = 0

    for pdf in pdfs:
        print(f"→ {pdf.name}")
        titulo = extrair_titulo_pdf(pdf)
        if not titulo:
            print("  [skip] Título não identificado\n")
            falhas += 1
            continue

        novo_nome = sanitize(titulo) + ".pdf"
        novo_path = pdf.with_name(novo_nome)

        if pdf.name == novo_nome:
            print("  [skip] Já está com o nome correto\n")
            continue

        # Evita sobrescrever
        if novo_path.exists() and novo_path.resolve() != pdf.resolve():
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            novo_nome = f"{sanitize(titulo)}__{timestamp}.pdf"
            novo_path = pdf.with_name(novo_nome)
            print(f"  [aviso] Nome já existe, usando sufixo: {novo_nome}")

        if dry_run:
            print(f"  [dry-run] {pdf.name}  →  {novo_nome}\n")
            continue

        try:
            pdf.rename(novo_path)
            print(f"  [ok] → {novo_nome}\n")
            renomeados += 1
        except Exception as e:
            print(f"  [erro] {e}\n")
            falhas += 1

    print("=" * 60)
    print(f"Renomeados: {renomeados} | Falhas/Skip: {falhas}")
    if dry_run:
        print("(modo dry-run: nenhuma alteração foi feita)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Renomeia PDFs pelo título do paper.")
    parser.add_argument("pasta", type=Path, help="Pasta (recursiva) com os PDFs")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem renomear")
    args = parser.parse_args()

    if not args.pasta.is_dir():
        print(f"Pasta inválida: {args.pasta}")
        sys.exit(1)

    renomear_pdfs(args.pasta, dry_run=args.dry_run)