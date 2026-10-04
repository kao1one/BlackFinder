#!/usr/bin/env python3
"""Verifica se o ambiente tem tudo que o BlackFinder precisa.

Só usa a biblioteca padrão. Código de saída 0 = tudo certo, 1 = há falhas.
"""
import importlib
import socket
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent
PORTA = 8765
MODULOS = ["argparse", "hashlib", "json", "pathlib", "http.server", "socket"]
OPCIONAIS = ["venv", "ensurepip"]
ARQUIVOS = ["localizador.html", "servir.py"]

falhas = 0


def ok(msg):
    print(f"[OK]    {msg}")


def falha(msg):
    global falhas
    falhas += 1
    print(f"[FALHA] {msg}")


def aviso(msg):
    print(f"[AVISO] {msg}")


v = sys.version_info
if v >= (3, 8):
    ok(f"Python {v.major}.{v.minor}.{v.micro}")
else:
    falha(f"Python {v.major}.{v.minor} é antigo demais (mínimo 3.8). No Termux: pkg install python")

for nome in MODULOS:
    try:
        importlib.import_module(nome)
        ok(f"módulo {nome}")
    except ImportError:
        falha(f"módulo {nome} ausente. No Termux: pkg install python")

try:
    from http.server import ThreadingHTTPServer  # noqa: F401
    ok("ThreadingHTTPServer disponível")
except ImportError:
    falha("ThreadingHTTPServer ausente (Python antigo?)")

for nome in OPCIONAIS:
    try:
        importlib.import_module(nome)
        ok(f"módulo {nome} (necessário só para o ambiente virtual)")
    except ImportError:
        aviso(f"módulo {nome} ausente: não dá para criar o ambiente virtual. Reinstale: pkg install python")

for nome in ARQUIVOS:
    arq = PASTA / nome
    if arq.is_file() and arq.stat().st_size > 0:
        ok(f"arquivo {nome} ({arq.stat().st_size} bytes)")
    else:
        falha(f"arquivo {nome} não encontrado ou vazio em {PASTA}")

html = PASTA / "localizador.html"
if html.is_file():
    try:
        txt = html.read_text(encoding="utf-8")
        if "<script>" in txt and "</script>" in txt:
            ok("localizador.html parece íntegro (UTF-8, com script)")
        else:
            falha("localizador.html está sem o bloco <script>: download incompleto?")
    except UnicodeDecodeError:
        falha("localizador.html não está em UTF-8: baixe de novo")

s = socket.socket()
try:
    s.bind(("127.0.0.1", PORTA))
    ok(f"porta {PORTA} livre")
except OSError:
    aviso(f"porta {PORTA} ocupada (servidor já rodando?). Use: python servir.py --porta 8766")
finally:
    s.close()

if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
    ok("rodando dentro de um ambiente virtual")
else:
    aviso("fora de ambiente virtual (normal nesta etapa)")

print()
print("Tudo certo." if not falhas else f"{falhas} falha(s) para corrigir.")
sys.exit(1 if falhas else 0)
