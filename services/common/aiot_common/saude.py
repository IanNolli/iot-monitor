"""Batimento para o healthcheck dos workers: grava um arquivo a cada poucos segundos."""

import asyncio
import sys
import time
from pathlib import Path

ARQUIVO = Path("/tmp/batimento")


async def manter_batimento(intervalo: float = 5.0) -> None:
    while True:
        ARQUIVO.write_text(str(time.time()))
        await asyncio.sleep(intervalo)


def verificar(limite_segundos: float = 30.0) -> None:
    """Usado como healthcheck: `python -m aiot_common.saude`."""
    try:
        idade = time.time() - float(ARQUIVO.read_text())
    except (OSError, ValueError):
        sys.exit(1)
    sys.exit(0 if idade < limite_segundos else 1)


if __name__ == "__main__":
    verificar()
