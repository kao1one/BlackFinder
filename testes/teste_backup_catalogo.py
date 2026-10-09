#!/usr/bin/env python3
"""Testes do backup do catálogo no servidor (rota /api/backup/catalogo) com dados FICTÍCIOS.

Uso, na pasta do projeto:  python testes/teste_backup_catalogo.py
       (ou)                python testes/teste_backup_catalogo.py --pasta OUTRA_PASTA
O servidor roda numa cópia temporária: nenhum dado real é lido ou gravado.
"""
import hashlib
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(sys.argv[sys.argv.index("--pasta") + 1]).resolve() if "--pasta" in sys.argv else Path(__file__).resolve().parent.parent
total = falhas = 0


def ok(nome, cond, extra=""):
    global total, falhas
    total += 1
    if not cond:
        falhas += 1
        print(f"  [FALHA] {nome}" + (f" => {extra}" if extra != "" else ""))


assina = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()
tmp = Path(tempfile.mkdtemp(prefix="bf_teste_"))
for f in RAIZ.glob("*.py"):
    if not f.name.startswith(("teste", "corrigir", "procurar", "backup_")):
        shutil.copy2(f, tmp)
for nome in ("localizador.html", "config.json"):
    if (RAIZ / nome).is_file():
        shutil.copy2(RAIZ / nome, tmp)
s = socket.socket(); s.bind(("127.0.0.1", 0)); porta = s.getsockname()[1]; s.close()
srv = subprocess.Popen([sys.executable, "servir.py", "--porta", str(porta)], cwd=tmp, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
base = f"http://127.0.0.1:{porta}"
for _ in range(60):
    try:
        urllib.request.urlopen(base + "/", timeout=1); break
    except Exception:
        time.sleep(0.1)
BK = tmp / "dados" / "backups"


def post(corpo, rota="/api/backup/catalogo", origem="auto", bruto=False):
    dados = corpo if bruto else json.dumps(corpo).encode()
    h = {"Content-Type": "application/json"}
    if origem == "auto":
        h["Origin"] = f"http://localhost:{porta}"
    elif origem:
        h["Origin"] = origem
    try:
        with urllib.request.urlopen(urllib.request.Request(base + rota, dados, h), timeout=10) as r:
            t = r.read().decode()
            return r.status, (json.loads(t) if t.startswith("{") else t)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, repr(e)


def envia(texto, **kw):
    return post({"conteudo": texto, "assinatura": assina(texto)}, **kw)


versoes = lambda: sorted(BK.glob("catalogo_*.csv")) if BK.is_dir() else []
try:
    LF = "codigo;local;descricao\nAB-10001;Corredor 1;\nAB-10002;Corredor 1;item mochila\n"
    CRLF = "codigo;local;descricao\r\nAB-10001;Corredor 1;\r\nAB-10002;Corredor 2;item mochila\r\n"
    ACENTO = "codigo;local;descricao\r\nAB-10001;Corredor 1 – frente às carteiras;ação\r\n"
    print("# Gravação")
    st, r = envia(LF)
    ok("cria a pasta dados/ sozinho se ela não existir", st == 200 and r.get("status") == "ok", (st, r))
    (tmp / "dados").mkdir(exist_ok=True)  # a partir daqui a pasta existe, para os demais testes não dependerem dela
    st, r = envia(LF)
    ok("conteúdo com \\n é gravado", st == 200 and r.get("status") in ("ok", "ja_existe"), (st, r))
    ok("arquivo idêntico ao enviado, byte a byte", len(versoes()) == 1 and versoes()[0].read_bytes() == LF.encode(), len(versoes()))
    st, r = envia(CRLF)
    ok("CSV com \\r\\n (formato do export do app) é gravado", st == 200 and r.get("status") == "ok", (st, r))
    ok("e fica idêntico, byte a byte", any(v.read_bytes() == CRLF.encode() for v in versoes()))
    st, r = envia(ACENTO)
    ok("acentos e travessão", st == 200 and any(v.read_bytes() == ACENTO.encode("utf-8") for v in versoes()), (st, r))
    print("# Duplicidade (compara com a ÚLTIMA versão)")
    n = len(versoes())
    st, r = envia(ACENTO)
    ok("mesma assinatura da última: não grava", st == 200 and r.get("status") == "ja_existe" and len(versoes()) == n, (st, r))
    st, r = envia(LF)
    ok("voltar a uma versão antiga (A, B, A) grava uma nova versão", st == 200 and r.get("status") == "ok" and len(versoes()) == n + 1, (st, r))
    ok("a última versão guardada é a que está no app agora", bool(versoes()) and versoes()[-1].stem.endswith(assina(LF)[:12]))
    print("# Entradas inválidas (devem dar 400/403, nunca derrubar a requisição)")
    cs = len(versoes())
    for nome, corpo, bruto, origem, esperado in [
        ("assinatura errada", {"conteudo": LF, "assinatura": "0" * 64}, False, "auto", 400),
        ("sem origem", {"conteudo": LF, "assinatura": assina(LF)}, False, None, 403),
        ("origem de outro site", {"conteudo": LF, "assinatura": assina(LF)}, False, "http://outro.site", 403),
        ("JSON que é lista", [1, 2], False, "auto", 400),
        ("JSON que é texto", "abc", False, "auto", 400),
        ("assinatura não é texto", {"conteudo": LF, "assinatura": 123}, False, "auto", 400),
        ("conteúdo não é texto", {"conteudo": 123, "assinatura": "a" * 64}, False, "auto", 400),
        ("conteúdo vazio", {"conteudo": "", "assinatura": assina("")}, False, "auto", 400),
        ("sem campos", {}, False, "auto", 400),
        ("assinatura com letras fora do hexadecimal", {"conteudo": LF, "assinatura": "z" * 64}, False, "auto", 400),
        ("JSON quebrado", b"{nao", True, "auto", 400),
        ("corpo vazio", b"", True, "auto", 400),
        ("corpo maior que 5 MB", b"x" * 5_000_100, True, "auto", (400, 0)),
    ]:
        st, r = post(corpo, bruto=bruto, origem=origem)
        ok(nome, st in (esperado if isinstance(esperado, tuple) else (esperado,)), (st, str(r)[:60]))
    ok("nada foi gravado pelas entradas inválidas", len(versoes()) == cs)
    print("# Limpeza e retenção")
    BK.mkdir(parents=True, exist_ok=True)
    (BK / "sobra.tmp").write_text("lixo")
    envia("codigo;local;descricao\nAB-1;X;\n")
    ok("sobra de gravação interrompida (.tmp) é apagada", not list(BK.glob("*.tmp")))
    for i in range(70):
        envia(f"codigo;local;descricao\nAB-{20000 + i};Corredor {i};\n")
    v = versoes()
    ok("mantém só as últimas 60 versões", len(v) == 60, len(v))
    ok("a mais recente é a última enviada", bool(v) and v[-1].stem.endswith(assina("codigo;local;descricao\nAB-20069;Corredor 69;\n")[:12]))
    print("# Concorrência")
    antes = len(versoes())
    res = []
    ths = [threading.Thread(target=lambda i=i: res.append(envia(f"codigo;local;descricao\nCD-{30000 + i};Z;\n"))) for i in range(12)]
    [t.start() for t in ths]; [t.join() for t in ths]
    ok("12 envios ao mesmo tempo, todos aceitos", all(r[0] == 200 for r in res), [r for r in res if r[0] != 200][:1])
    ok("sem arquivo temporário sobrando", not list(BK.glob("*.tmp")))
    ok("todos os 12 foram gravados (e a retenção continua em 60)", len(versoes()) == min(60, antes + 12), len(versoes()))
    print("# Falha: disco cheio (escrita falha no meio)")
    import resource, signal
    def _disco_cheio():
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_FSIZE, (1_000_000, 1_000_000))
    s2 = socket.socket(); s2.bind(("127.0.0.1", 0)); p2 = s2.getsockname()[1]; s2.close()
    srv2 = subprocess.Popen([sys.executable, "servir.py", "--porta", str(p2)], cwd=tmp,
                            preexec_fn=_disco_cheio, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{p2}/", timeout=1); break
        except Exception:
            time.sleep(0.1)
    def post2(corpo):
        d = json.dumps(corpo).encode()
        h = {"Content-Type": "application/json", "Origin": f"http://localhost:{p2}"}
        try:
            with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{p2}/api/backup/catalogo", d, h), timeout=15) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()
    grande = "x" * 2_000_000
    n0 = len(versoes())
    st, r = post2({"conteudo": grande, "assinatura": assina(grande)})
    ok("arquivo maior que o espaco: responde 500 tratado", st == 500 and "erro ao gravar" in r, (st, str(r)[:60]))
    ok("nenhuma versao nova foi gravada", len(versoes()) == n0, len(versoes()))
    st, r = post2({"conteudo": LF, "assinatura": assina(LF)})
    ok("gravacao pequena valida continua funcionando", st == 200 and json.loads(r).get("status") in ("ok", "ja_existe"), (st, str(r)[:60]))
    ok("arquivo temporario pela metade foi apagado na proxima gravacao", not list(BK.glob("*.tmp")))
    srv2.terminate()
    try:
        srv2.wait(5)
    except Exception:
        srv2.kill()
    print("# Regressão: o que já existia continua funcionando")
    st, r = post([{"id": "t1", "cliente": "X", "itens": [["AB-1", 1, ""]], "naoEnc": []}], rota="/api/pedidos")
    ok("POST /api/pedidos", st == 200 and r == {"salvos": ["t1"]}, (st, r))
    ok("pedido gravado no arquivo certo", (tmp / "dados" / "pedidos.jsonl").is_file())
    st, r = post([{"id": "t1"}], rota="/api/pedidos", origem="http://outro.site")
    ok("pedidos: origem de outro site continua negada", st == 403)
    for rota, cod in [("/", 200), ("/sw.js", 200), ("/manifest.json", 200), ("/nao-existe", 404)]:
        try:
            c = urllib.request.urlopen(base + rota, timeout=5).status
        except urllib.error.HTTPError as e:
            c = e.code
        ok(f"GET {rota}", c == cod, c)
    ok("o servidor continua vivo depois de tudo", srv.poll() is None)
finally:
    srv.terminate()
    try:
        srv.wait(5)
    except Exception:
        srv.kill()
    err = srv.stderr.read().decode(errors="replace") if srv.stderr else ""
    shutil.rmtree(tmp, ignore_errors=True)
if "Traceback" in err:
    falhas += 1; total += 1
    print("  [FALHA] o servidor registrou erro interno (exceção não tratada):")
    print("   " + err.strip().splitlines()[-1][:140])
print(f"\n{total - falhas}/{total} verificações do backup ok" + (f" | {falhas} FALHA(S)" if falhas else ""))
sys.exit(1 if falhas else 0)
