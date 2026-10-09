#!/usr/bin/env python3
"""Serve o Localizador em http://localhost:8765 (só stdlib, sem dependências).

Depois do primeiro carregamento o app fica em cache (service worker) e abre
offline, mesmo com este servidor desligado. Rode de novo só para atualizar.
"""
import argparse
import hashlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HTML = Path(__file__).resolve().parent / "localizador.html"
DADOS = Path(__file__).resolve().parent / "dados"
TRAVA = threading.Lock()
try:
    import supervisor
except ImportError:
    supervisor = None

MANIFEST = json.dumps({
    "name": "Localizador",
    "short_name": "Localizador",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#000000",
    "theme_color": "#000000",
}).encode()

SW = """const C='loc-__V__';
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(['/','/manifest.json'])).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C).map(x=>caches.delete(x)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{if(e.request.method!=='GET'||e.request.url.includes('/api/'))return;e.respondWith(fetch(e.request).then(res=>{if(res.ok){const c=res.clone();caches.open(C).then(x=>x.put(e.request,c))}return res}).catch(()=>caches.match(e.request,{ignoreSearch:true}).then(r=>r||caches.match('/')).then(r=>r||new Response('offline',{status:503}))))});
"""


class Handler(BaseHTTPRequestHandler):
    def _enviar(self, corpo, tipo, status=200):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        rota = self.path.split("?")[0]
        try:
            if rota in ("/", "/index.html"):
                self._enviar(HTML.read_bytes(), "text/html; charset=utf-8")
            elif rota == "/sw.js":
                versao = hashlib.sha1(HTML.read_bytes() + SW.encode()).hexdigest()[:12]
                self._enviar(SW.replace("__V__", versao).encode(), "application/javascript; charset=utf-8")
            elif rota == "/api/alertas":
                porta = self.server.server_address[1]
                if self.headers.get("Host", "") not in (f"localhost:{porta}", f"127.0.0.1:{porta}"):
                    self._enviar(b"host negado", "text/plain; charset=utf-8", 403)
                else:
                    lista = supervisor.ultimos(DADOS) if supervisor else []
                    self._enviar(json.dumps(lista, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            elif rota == "/manifest.json":
                self._enviar(MANIFEST, "application/manifest+json")
            else:
                self._enviar(b"nao encontrado", "text/plain; charset=utf-8", 404)
        except OSError as e:
            self._enviar(f"erro ao ler arquivo: {e}".encode(), "text/plain; charset=utf-8", 500)

    def do_POST(self):
        rota = self.path.split("?")[0]
        if rota == "/api/backup/catalogo":
            return self._backup_catalogo()
        if rota != "/api/pedidos":
            return self._enviar(b"nao encontrado", "text/plain; charset=utf-8", 404)
        porta = self.server.server_address[1]
        if self.headers.get("Origin", "") not in (f"http://localhost:{porta}", f"http://127.0.0.1:{porta}"):
            return self._enviar(b"origem negada", "text/plain; charset=utf-8", 403)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= 2_000_000:
                raise ValueError("tamanho")
            lote = json.loads(self.rfile.read(n))
            if not isinstance(lote, list) or not all(isinstance(x, dict) and isinstance(x.get("id"), str) for x in lote):
                raise ValueError("formato")
        except ValueError:
            return self._enviar(b"requisicao invalida", "text/plain; charset=utf-8", 400)
        try:
            with TRAVA:
                DADOS.mkdir(exist_ok=True)
                arq = DADOS / "pedidos.jsonl"
                linhas = {}
                if arq.is_file():
                    for linha in arq.read_text(encoding="utf-8").splitlines():
                        try:
                            linhas[json.loads(linha)["id"]] = linha
                        except (ValueError, KeyError, TypeError):
                            linhas[f"_ruim{len(linhas)}"] = linha  # linha corrompida: preservada intacta
                mudou = False
                for x in lote:
                    nova = json.dumps(x, ensure_ascii=False)
                    if linhas.get(x["id"]) != nova:  # pedido novo ou corrigido no app
                        linhas[x["id"]] = nova
                        mudou = True
                if mudou:
                    tmp = arq.with_suffix(".tmp")
                    tmp.write_text("\n".join(linhas.values()) + "\n", encoding="utf-8")
                    tmp.replace(arq)
        except OSError as e:
            return self._enviar(f"erro ao gravar: {e}".encode(), "text/plain; charset=utf-8", 500)
        self._enviar(json.dumps({"salvos": [x["id"] for x in lote]}).encode(), "application/json")

    def _backup_catalogo(self):
        """Guarda uma versão datada do catálogo, só se diferir da ÚLTIMA versão (backup v2)."""
        porta = self.server.server_address[1]
        if self.headers.get("Origin", "") not in (f"http://localhost:{porta}", f"http://127.0.0.1:{porta}"):
            return self._enviar(b"origem negada", "text/plain; charset=utf-8", 403)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= 5_000_000:
                raise ValueError("tamanho")
            dados = json.loads(self.rfile.read(n))
            if not isinstance(dados, dict):
                raise ValueError("formato")
            conteudo, assinatura = dados.get("conteudo"), dados.get("assinatura")
            if not isinstance(conteudo, str) or not conteudo:
                raise ValueError("conteudo")
            if not isinstance(assinatura, str) or len(assinatura) != 64 or any(c not in "0123456789abcdef" for c in assinatura):
                raise ValueError("assinatura")
            bruto = conteudo.encode("utf-8")
        except ValueError:
            return self._enviar(b"requisicao invalida", "text/plain; charset=utf-8", 400)
        if hashlib.sha256(bruto).hexdigest() != assinatura:
            return self._enviar(b"assinatura invalida", "text/plain; charset=utf-8", 400)
        try:
            with TRAVA:
                from datetime import datetime
                pasta = DADOS / "backups"
                pasta.mkdir(parents=True, exist_ok=True)
                for sobra in pasta.glob("*.tmp"):
                    sobra.unlink(missing_ok=True)
                versoes = sorted(pasta.glob("catalogo_*.csv"))
                if versoes and versoes[-1].stem.endswith(assinatura[:12]):
                    return self._enviar(json.dumps({"status": "ja_existe", "arquivo": versoes[-1].name}).encode(), "application/json")
                nome = f"catalogo_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{assinatura[:12]}.csv"
                destino = pasta / nome
                tmp = destino.with_suffix(".tmp")
                tmp.write_bytes(bruto)
                if hashlib.sha256(tmp.read_bytes()).hexdigest() != assinatura:
                    tmp.unlink(missing_ok=True)
                    return self._enviar(b"falha na verificacao", "text/plain; charset=utf-8", 500)
                tmp.replace(destino)
                for antigo in sorted(pasta.glob("catalogo_*.csv"))[:-60]:
                    antigo.unlink(missing_ok=True)
            return self._enviar(json.dumps({"status": "ok", "arquivo": nome}).encode(), "application/json")
        except OSError as e:
            return self._enviar(f"erro ao gravar: {e}".encode(), "text/plain; charset=utf-8", 500)

    def log_message(self, *args):
        pass



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=8765)
    porta = ap.parse_args().porta
    if not HTML.is_file():
        sys.exit(f"Arquivo não encontrado: {HTML}")
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    except OSError as e:
        sys.exit(f"Não consegui abrir a porta {porta}: {e}\n(já está rodando? use --porta)")
    if supervisor:
        supervisor.Supervisor(DADOS).start()
    print(f"Rodando em http://localhost:{porta}  (Ctrl+C para parar)" + ("  [supervisor ativo]" if supervisor else ""))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
