#!/usr/bin/env python3
"""Confere se é seguro commitar: nenhum dado do catálogo nos arquivos versionáveis.

Rode antes de cada commit/push:  python checar_repo.py
Código de saída 0 = seguro, 1 = há problema.
"""
import csv
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent
EXIGIDOS = ["catalogo*", "pedidos*", "dados/", "*.csv", ".venv/"]          # linhas obrigatórias no .gitignore
DADOS = ["catalogo*", "pedidos*", "*.csv", "*.tsv", "*.xlsx", "*.jsonl"]    # nomes que são banco de dados
DIRS_IGNORADOS = {".git", ".venv", "__pycache__", "dados"}
COD = re.compile(r"\b[A-Za-z]{2}\s*-?\s*\d{4,6}\b")

problemas = 0


def ok(m):
    print(f"[OK]    {m}")


def ruim(m):
    global problemas
    problemas += 1
    print(f"[FALHA] {m}")


def aviso(m):
    print(f"[AVISO] {m}")


def e_dado(nome):
    return any(fnmatch.fnmatch(nome.lower(), p) for p in DADOS)


def git(*args):
    try:
        r = subprocess.run(["git", *args], cwd=PASTA, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def norm(c):
    return re.sub(r"[^A-Za-z0-9]", "", c).upper()


# 1. .gitignore
gi = PASTA / ".gitignore"
linhas = {l.strip() for l in gi.read_text(encoding="utf-8").splitlines()} if gi.is_file() else set()
for e in EXIGIDOS:
    (ok if e in linhas else ruim)(f".gitignore {'tem' if e in linhas else 'NÃO tem'} a linha '{e}'")

# 2. Dados reais locais para comparar
codigos, locais = set(), set()
for arq in PASTA.iterdir():
    if not (arq.is_file() and e_dado(arq.name)):
        continue
    try:
        if arq.suffix.lower() == ".csv":
            with open(arq, encoding="utf-8-sig", newline="") as f:
                for lin in list(csv.reader(f, delimiter=";"))[1:]:
                    if lin:
                        codigos.add(norm(lin[0]))
                    if len(lin) > 1 and len(lin[1].strip()) >= 4:
                        locais.add(lin[1].strip().lower())
        elif arq.suffix.lower() in (".txt", ".tsv"):
            texto = arq.read_text(encoding="utf-8-sig", errors="ignore")
            codigos.update(norm(m.group(0)) for m in COD.finditer(texto))
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        aviso(f"não consegui ler {arq.name} para comparar: {e}")
if codigos:
    ok(f"comparando contra {len(codigos)} códigos e {len(locais)} locais do catálogo local")
else:
    aviso("nenhum catálogo local encontrado nesta pasta: não dá para comparar conteúdo")

# 3. Conteúdo dos arquivos versionáveis
for arq in sorted(PASTA.rglob("*")):
    if not arq.is_file() or any(p in DIRS_IGNORADOS for p in arq.relative_to(PASTA).parts) or e_dado(arq.name):
        continue
    try:
        texto = arq.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        continue
    achou = {norm(m.group(0)) for m in COD.finditer(texto)} & codigos
    if achou:
        ruim(f"{arq.name} contém código(s) do catálogo: {', '.join(sorted(achou)[:5])}")
    baixo = texto.lower()
    loc = [l for l in locais if l in baixo]
    if loc:
        ruim(f"{arq.name} contém local(is) do catálogo: {', '.join(sorted(loc)[:3])}")
    if arq.name != "checar_repo.py" and not (achou or loc):
        ok(f"{arq.name} limpo")

# 4. Git: o que está versionado e o histórico
if git("rev-parse", "--is-inside-work-tree") is None:
    aviso("pasta ainda não é um repositório git (ou git não instalado): checagem de versionamento pulada")
else:
    rastreados = (git("ls-files") or "").splitlines()
    ruins = [f for f in rastreados if e_dado(Path(f).name) or f.startswith("dados/")]
    (ruim if ruins else ok)(f"arquivos de dados versionados: {ruins}" if ruins else "nenhum arquivo de dados versionado")
    hist = {f for f in (git("log", "--all", "--name-only", "--pretty=format:") or "").splitlines() if f and (e_dado(Path(f).name) or f.startswith("dados/"))}
    (ruim if hist else ok)(f"HISTÓRICO contém dados: {sorted(hist)} (apagar o arquivo não basta; avise antes de dar push)" if hist else "histórico sem arquivos de dados")

print()
print("Seguro para commitar." if not problemas else f"{problemas} problema(s): NÃO dê push.")
sys.exit(1 if problemas else 0)
