"""Modelo físico do equipamento monitorado: o compressor da geladeira.

O mesmo modelo é usado pelo simulador ao vivo e pelo gerador de dados sintéticos,
para que a IA treinada com dados sintéticos funcione com a telemetria em tempo real.
As funções aceitam escalares ou arrays numpy.

Tempo simulado: cada leitura representa PASSO_MINUTOS minutos de operação.
"""

import numpy as np

PASSO_MINUTOS = 5
LEITURAS_POR_DIA = 24 * 60 // PASSO_MINUTOS  # 288
VARIAVEIS = ("vibracao", "corrente", "temperatura")  # mm/s, A, °C

# Efeito máximo de cada modo de falha (degradação = 1) em (vibração, corrente, temperatura)
MODOS_FALHA = {
    "rolamento": (6.0, 0.35, 6.0),
    "entupimento": (1.0, 0.60, 18.0),
    "superaquecimento": (1.5, 0.90, 25.0),
    "desbalanceamento": (5.0, 0.25, 4.0),
}

# Desvio-padrão do ruído com nível de ruído 1.0
RUIDO_BASE = np.array([0.15, 0.03, 0.6])


def hora_do_dia(passo):
    return (np.asarray(passo) * PASSO_MINUTOS / 60.0) % 24.0


def temperatura_ambiente(passo):
    """Ciclo diário: mínima de madrugada, máxima no meio da tarde."""
    hora = hora_do_dia(passo)
    return 24.0 + 4.0 * np.sin(2 * np.pi * (hora - 9.0) / 24.0)


def sortear_parametros(rng: np.random.Generator, n: int = 1) -> dict:
    """Diferenças de fabricação entre máquinas (geram sobreposição entre saudáveis e doentes)."""
    return {
        "v0": rng.normal(2.0, 0.25, n),
        "c0": rng.normal(1.2, 0.08, n),
        "t0": rng.normal(45.0, 2.0, n),
        "escala": rng.uniform(0.7, 1.3, n),
    }


def valores(passo, params: dict, degradacao, modo: str | None, rng: np.random.Generator, ruido: float = 1.0):
    """Retorna array (..., 3) com vibração, corrente e temperatura medidas."""
    passo = np.asarray(passo)
    amb = temperatura_ambiente(passo)
    hora = hora_do_dia(passo)
    vib = params["v0"] + 0.15 * np.sin(2 * np.pi * hora / 24.0)
    cor = params["c0"] + 0.03 * (amb - 24.0)
    tmp = params["t0"] + 0.8 * (amb - 24.0)
    base = np.stack(np.broadcast_arrays(vib, cor, tmp), axis=-1).astype(float)

    if modo is not None:
        efeito = np.asarray(MODOS_FALHA[modo]) * np.asarray(params["escala"], dtype=float)[..., None]
        d = np.asarray(degradacao, dtype=float)[..., None] ** 1.3
        base = base + efeito * d
        if modo == "desbalanceamento":  # oscilação típica de desbalanceamento
            base[..., 0] += 0.8 * np.asarray(degradacao) * np.sin(passo * 0.7)

    ruido_arr = rng.normal(0.0, 1.0, base.shape) * RUIDO_BASE * ruido
    return base + ruido_arr
