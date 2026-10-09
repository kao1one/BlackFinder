#!/usr/bin/env python3
"""Supervisor do BlackFinder: só LÊ os pedidos e AVISA. Não altera pedidos nem o app.

Roda como tarefa em segundo plano dentro do servir.py. Escreve apenas dados/alertas.jsonl
(o próprio registro de avisos) e dispara notificações do Termux.
Teste manual:  python supervisor.py --uma-vez
"""
import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
import json
from eventos import registrar

# Carrega configuração externa (Fase 1)
try:
    with open(Path(__file__).resolve().parent / "config.json", encoding="utf-8") as f:
        _cfg = json.load(f)
    _lim = _cfg.get("limites", {})
except Exception:
    _lim = {}

MIN_SUP = _lim.get("min_suporte_regra", 3)
MIN_CONF = _lim.get("min_confianca_regra", 0.5)
LONGO_MIN = _lim.get("pedido_longo_minutos", 45)
JANELA = _lim.get("janela_pedidos", 20)
INTERVALO = _lim.get("intervalo_supervisor_segundos", 60)
MAX_NOTIF = _lim.get("max_notificacoes_ciclo", 3)
DIA = 86_400_000

def ler_catalogo(pasta):
    """Lê o catálogo oficial e devolve o set de códigos válidos."""
    arq = Path(pasta) / "catalogo.csv"
    if not arq.is_file():
        return None
    codigos = set()
    try:
        with arq.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cod = (row.get("Código") or row.get("Codigo") or "").strip()
                if cod:
                    codigos.add(cod)
    except Exception:
        return None
    return codigos if codigos else None


def ler(arq):
    """Lê os pedidos (somente leitura). Devolve (pedidos_validos, linhas_ruins)."""
    ok, ruins = [], 0
    if not arq.is_file():
        return ok, ruins
    for linha in arq.read_text(encoding="utf-8").splitlines():
        if not linha.strip():
            continue
        try:
            p = json.loads(linha)
            assert isinstance(p, dict) and isinstance(p["id"], str)
            assert isinstance(p["ini"], (int, float)) and isinstance(p["fim"], (int, float))
            assert all(isinstance(x, list) and len(x) == 2 for x in p["itens"])
            p["naoEnc"] = [x for x in p.get("naoEnc", []) if isinstance(x, list) and len(x) == 2]
            ok.append(p)
        except (ValueError, AssertionError, KeyError, TypeError):
            ruins += 1
    return ok, ruins


def regras(ps):
    """Itens que saem juntos: (A, B, pedidos_com_ambos, confiança P(B|A))."""
    un, par = Counter(), Counter()
    for p in ps:
        s = sorted({x[0] for x in p["itens"]})
        un.update(s)
        if len(s) <= 40:
            for i, a in enumerate(s):
                for b in s[i + 1:]:
                    par[(a, b)] += 1
    r = []
    for (a, b), n in par.items():
        if n >= MIN_SUP:
            for x, y in ((a, b), (b, a)):
                if n / un[x] >= MIN_CONF:
                    r.append((x, y, n, n / un[x]))
    return sorted(r, key=lambda t: (-t[3], -t[2], t[0], t[1]))


def _cli(p):
    return (p.get("cliente") or "").strip().lower()


def analisar(ps, ruins, agora, catalogo=None):
    """Função pura: devolve a lista de anomalias {chave, titulo, texto}."""
    A = []
    dia = datetime.fromtimestamp(agora / 1000).strftime("%Y-%m-%d")

    def add(chave, titulo, texto):
        A.append({"chave": chave, "titulo": titulo, "texto": texto})

    if catalogo is None:
        add(f"cat:ausente:{dia}", "Catálogo oficial ausente",
            "Arquivo dados/catalogo.csv não encontrado ou está vazio. Supervisor sem referência oficial.")
    else:
        c_naoenc_validos = Counter()
        c_itens_invalidos = Counter()

        for p in ps:
            if agora - p["fim"] < 7 * DIA:
                for x in p.get("naoEnc", []):
                    cod = x[0]
                    if cod in catalogo:
                        c_naoenc_validos[cod] += 1
                for x in p.get("itens", []):
                    cod = x[0]
                    if cod not in catalogo:
                        c_itens_invalidos[cod] += 1

        for cod, n in sorted(c_naoenc_validos.items()):
            if n >= 2:
                add(f"busca:{cod}:{dia}", "Código existe no catálogo mas foi marcado como não encontrado",
                    f"{cod} apareceu {n} vezes em naoEnc nos últimos 7 dias, porém existe no catálogo oficial. Possível falha na busca.")

        for cod, n in sorted(c_itens_invalidos.items()):
            if n >= 2:
                add(f"invalido:{cod}:{dia}", "Código usado em pedidos não existe no catálogo oficial",
                    f"{cod} apareceu {n} vezes em pedidos nos últimos 7 dias, mas não está no catálogo oficial.")

    if ruins:
        add(f"ruins:{dia}", "Dados corrompidos", f"{ruins} linha(s) inválida(s) em pedidos.jsonl.")
    ps = sorted(ps, key=lambda p: p["ini"])
    rec = [p for p in ps if agora - p["fim"] < DIA]
    for i, p in enumerate(rec):
        m = (p["fim"] - p["ini"]) / 60000
        nome = p.get("cliente") or "(sem cliente)"
        if m < 0:
            add(f"neg:{p['id']}", "Horário inconsistente", f"Pedido de {nome} termina antes de começar.")
        elif m > LONGO_MIN:
            add(f"longo:{p['id']}", "Pedido muito longo", f"Pedido de {nome} durou {m:.0f} min. Finalizar esquecido?")
        s = frozenset(x[0] for x in p["itens"])
        if _cli(p) and s:
            for q in rec[:i]:
                if _cli(q) == _cli(p) and frozenset(x[0] for x in q["itens"]) == s and abs(p["ini"] - q["ini"]) < 10 * 60000:
                    add(f"dup:{p['id']}", "Possível pedido duplicado", f"{nome}: mesmos itens em menos de 10 min.")
                    break
    ult = ps[-JANELA:]
    if len(ult) >= 10:
        it = sum(len(p["itens"]) for p in ult)
        nn = sum(len(p["naoEnc"]) for p in ult)
        if it + nn >= 10 and nn / (it + nn) > 0.30:
            add(f"nf:{dia}", "Muitos códigos não encontrados", f"{nn / (it + nn):.0%} nos últimos {len(ult)} pedidos.")
        sem = sum(1 for p in ult if not _cli(p) or not (p.get("regiao") or "").strip())
        if sem / len(ult) > 0.5:
            add(f"qual:{dia}", "Pedidos sem cliente/região", f"{sem} dos últimos {len(ult)} pedidos sem cliente ou região: os relatórios perdem valor.")
    c7 = Counter()
    for p in ps:
        if agora - p["fim"] < 7 * DIA:
            c7.update({x[0] for x in p["naoEnc"]})
    for cod, n in sorted(c7.items()):
        if n >= 3:
            add(f"cod:{cod}:{dia}", "Código não encontrado recorrente", f"{cod} em {n} pedidos nos últimos 7 dias. Catálogo desatualizado?")
    if len(ps) >= 30:
        k = int(len(ps) * 0.7)
        obs = hit = 0
        esp = 0.0
        for x, y, _, cf in regras(ps[:k])[:20]:
            for p in ps[k:]:
                s = {i[0] for i in p["itens"]}
                if x in s:
                    obs += 1
                    esp += cf
                    hit += y in s
        if obs >= 10 and hit / obs < 0.5 * (esp / obs):
            add(f"agente:{dia}", "Indicações do agente não se confirmam", f"Previsto ~{esp / obs:.0%}, confirmado {hit / obs:.0%} em {obs} casos de teste.")
    return A


def notificar_termux(titulo, texto):
    exe = shutil.which("termux-notification")
    if not exe:
        return False
    nid = str(int(hashlib.sha1((titulo + texto).encode()).hexdigest()[:6], 16))
    try:
        subprocess.run([exe, "--title", f"BlackFinder: {titulo}", "--content", texto, "--id", nid, "--priority", "high"],
                       timeout=15, check=False, capture_output=True)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def ultimos(pasta, n=50):
    arq = Path(pasta) / "alertas.jsonl"
    out = []
    if arq.is_file():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(linha))
            except ValueError:
                pass
    return out[-n:]


class Supervisor(threading.Thread):
    def __init__(self, pasta, notificar=notificar_termux):
        super().__init__(daemon=True)
        self.pasta, self.notificar, self.parar = Path(pasta), notificar, threading.Event()

    def ciclo(self, agora=None):
        agora = agora or int(time.time() * 1000)
        ps, ruins = ler(self.pasta / "pedidos.jsonl")
        catalogo = ler_catalogo(self.pasta)
        vistos = {a.get("chave") for a in ultimos(self.pasta, 100000)}
        novos = [a for a in analisar(ps, ruins, agora, catalogo) if a["chave"] not in vistos]
        if novos:
            self.pasta.mkdir(exist_ok=True)
            with (self.pasta / "alertas.jsonl").open("a", encoding="utf-8") as f:
                for a in novos:
                    a["ts"] = agora
                    f.write(json.dumps(a, ensure_ascii=False) + "\n")
            for a in novos[:MAX_NOTIF]:
                self.notificar(a["titulo"], a["texto"])
            if len(novos) > MAX_NOTIF:
                self.notificar("Mais alertas", f"+{len(novos) - MAX_NOTIF} alerta(s): abra a aba Análise no app.")
                registrar("supervisor_ciclo", f"novos_alertas={len(novos)}")
        return novos

    def run(self):
        while True:
            try:
                self.ciclo()
            except Exception as e:
                print(f"[supervisor] erro: {e}")
            if self.parar.wait(INTERVALO):
                break


if __name__ == "__main__":
    import tempfile

    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--uma-vez", action="store_true", help="verifica os pedidos reais agora")
    g.add_argument("--demo", action="store_true", help="simula um pedido de 95 min em pasta temporária e dispara uma notificação real")
    args = ap.parse_args()
    if args.demo:
        agora = int(time.time() * 1000)
        with tempfile.TemporaryDirectory() as t:
            demo = {"id": "demo", "ini": agora - 95 * 60000, "fim": agora - 60000, "cliente": "Cliente de teste",
                    "regiao": "Teste", "itens": [["AB-00000", 1]], "naoEnc": []}
            (Path(t) / "pedidos.jsonl").write_text(json.dumps(demo) + "\n", encoding="utf-8")
            novos = Supervisor(Path(t)).ciclo(agora)
        if not shutil.which("termux-notification"):
            print("AVISO: termux-notification não encontrado: nenhuma notificação foi enviada.")
    else:
        novos = Supervisor(Path(__file__).resolve().parent / "dados").ciclo()
    for a in novos:
        print(f"- {a['titulo']}: {a['texto']}")
    print("Demonstração concluída (nenhum dado real foi usado)." if args.demo else "Verificação concluída.")
