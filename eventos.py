#!/usr/bin/env python3
"""Registro leve de eventos – Fase 1.
Só append. Mínimo impacto em performance.
"""

import json
import time
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024  # 2 MB – rotação simples
ARQ = Path(__file__).resolve().parent / "dados" / "eventos.jsonl"


def registrar(tipo: str, detalhe: str = "", **extra):
    """Registra um evento. Falha silenciosa se der erro (nunca quebra o app)."""
    try:
        ARQ.parent.mkdir(exist_ok=True)
        # Rotação simples por tamanho
        if ARQ.is_file() and ARQ.stat().st_size > MAX_BYTES:
            antigo = ARQ.with_suffix(".jsonl.old")
            if antigo.exists():
                antigo.unlink()
            ARQ.rename(antigo)

        evento = {
            "ts": int(time.time() * 1000),
            "tipo": tipo,
            "detalhe": detalhe,
            **extra
        }
        with ARQ.open("a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False) + "\n")
    except Exception:
        pass  # nunca interrompe o fluxo principal
