#!/usr/bin/env python3
"""Converte a lista em texto livre (um local por bloco) em catalogo.csv para o BlackFinder.

Uso: python converter.py [arquivo_bruto.txt]   (padrão: catalogo_bruto.txt ao lado deste script)
Regras: linha sem código = nome do local; linha com códigos = produtos desse local.
Códigos são padronizados como AA-12345 (aceita 'AB 12345', 'AB12345', 'AB- 12345').
"""
import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

PASTA = Path(__file__).resolve().parent
COD = re.compile(r"\b([A-Za-z]{2})\s*-?\s*(\d{4,6})\b")
ROTULO = re.compile(r"^\s*c[oó]digos?[\s.:]*", re.I)
OBS = re.compile(r"\bOBS\b[:\s]*", re.I)
MOCHILA = re.compile(r"mochila", re.I)


def achar(txt):
    return [(f"{m.group(1).upper()}-{m.group(2)}", m.group(0)) for m in COD.finditer(txt)]


def main():
    bruto = Path(sys.argv[1]) if len(sys.argv) > 1 else PASTA / "catalogo_bruto.txt"
    if not bruto.is_file():
        sys.exit(f"Arquivo não encontrado: {bruto}")

    itens = {}  # (codigo, local) -> lista de notas
    local, vazio = None, False
    sem_codigo, repetidos, corrigidos = [], [], 0

    for linha in bruto.read_text(encoding="utf-8-sig").splitlines():
        limpa = linha.replace("✅", "").strip()
        if not limpa:
            continue
        corpo = ROTULO.sub("", limpa).strip()
        if not corpo:
            continue  # linha só com o rótulo "Código."
        if not COD.search(corpo):
            if local and vazio:
                sem_codigo.append(local)
            local, vazio = limpa.rstrip(" .:"), True
            continue
        if local is None:
            sys.exit(f"Códigos antes de qualquer local: {limpa[:60]}")
        vazio = False

        obs = None
        m = OBS.search(corpo)
        if m:
            obs, _, depois = corpo[m.end():].partition(",")
            segs = corpo[:m.start()].split(",") + depois.split(",")
        else:
            segs = corpo.split(",")

        ultimo = None
        for seg in segs:
            for cod, original in achar(seg):
                if cod != original.strip():
                    corrigidos += 1
                chave = (cod, local)
                if chave in itens:
                    repetidos.append(f"{cod} em '{local}'")
                notas = itens.setdefault(chave, [])
                if MOCHILA.search(seg) and "Mochila" not in notas:
                    notas.append("Mochila")
                ultimo = cod
        if obs and obs.strip():
            alvos = [c for c, _ in achar(obs)] or ([ultimo] if ultimo else [])
            for cod in alvos:
                notas = itens.setdefault((cod, local), [])
                notas.append("OBS: " + obs.strip())

    if local and vazio:
        sem_codigo.append(local)
    if not itens:
        sys.exit("Nenhum código encontrado.")

    saida = bruto.with_name("catalogo.csv")
    with open(saida, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["codigo", "local", "descricao"])
        for (cod, loc), notas in itens.items():
            w.writerow([cod, loc, " | ".join(notas)])

    por_cod = defaultdict(list)
    for cod, loc in itens:
        por_cod[cod].append(loc)
    multi = {c: l for c, l in por_cod.items() if len(l) > 1}
    locais = {loc for _, loc in itens}

    print(f"{len(itens)} linhas em {len(locais)} locais ({len(por_cod)} códigos únicos) -> {saida}")
    print(f"{corrigidos} códigos padronizados (espaço/hífen).")
    if repetidos:
        print("Repetidos no mesmo local (unificados):", "; ".join(repetidos))
    for c, l in multi.items():
        print(f"ATENÇÃO {c} está em mais de um local: {' / '.join(l)}")
    if sem_codigo:
        print("Linhas tratadas como local, mas sem código (confira):", "; ".join(sem_codigo))

    dl = Path.home() / "storage" / "downloads"
    if dl.is_dir() and saida.parent != dl:
        try:
            shutil.copy2(saida, dl / "catalogo.csv")
            print(f"Cópia também em {dl / 'catalogo.csv'} (para importar pelo Chrome).")
        except OSError as e:
            print(f"Não consegui copiar para Downloads: {e}")


if __name__ == "__main__":
    main()
