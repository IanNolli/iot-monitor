"""Gerador de dados sintéticos massivos: simula a vida inteira de vários compressores.

Gera em blocos com numpy (um equipamento por vez), nunca ponto a ponto.
Cada linha de treino guarda os rótulos de verdade (saúde e vida útil restante),
que NUNCA são enviados na telemetria em tempo real.
"""

import json
import time
from pathlib import Path

import numpy as np
from aiot_common import equipamento as eq

DIR_DADOS = Path("/dados")
VIDA_UTIL_MAXIMA_H = 240.0  # rótulo limitado a 10 dias ("mais de 10 dias" = sem sinal de falha)
TETO_LEITURAS = 20_000_000  # teto para não travar a máquina

PADRAO = {
    "equipamentos": 60,
    "dias": 60,
    "sensores": {"vibracao": 1, "corrente": 1, "temperatura": 1},
    "pct_falha": 50.0,
    "modos_falha": list(eq.MODOS_FALHA),
    "falhas_sensor": ["deriva", "travamento"],
    "pct_falha_sensor": 10.0,
    "ruido": 1.0,
    "pct_faltantes": 1.0,
    "pct_outliers": 0.5,
    "semente": 42,
}


def validar(parametros: dict) -> dict:
    p = {**PADRAO, **{k: v for k, v in parametros.items() if v is not None}}
    p["sensores"] = {**PADRAO["sensores"], **(parametros.get("sensores") or {})}
    p["equipamentos"] = int(np.clip(p["equipamentos"], 1, 500))
    p["dias"] = int(np.clip(p["dias"], 1, 365))
    for var in eq.VARIAVEIS:
        p["sensores"][var] = int(np.clip(p["sensores"][var], 1, 3))
    p["pct_falha"] = float(np.clip(p["pct_falha"], 0, 100))
    p["modos_falha"] = [m for m in p["modos_falha"] if m in eq.MODOS_FALHA] or ["rolamento"]
    p["falhas_sensor"] = [f for f in p["falhas_sensor"] if f in ("deriva", "travamento")]
    p["pct_falha_sensor"] = float(np.clip(p["pct_falha_sensor"], 0, 100))
    p["ruido"] = float(np.clip(p["ruido"], 0, 3))
    p["pct_faltantes"] = float(np.clip(p["pct_faltantes"], 0, 20))
    p["pct_outliers"] = float(np.clip(p["pct_outliers"], 0, 10))
    p["semente"] = int(p["semente"])
    linhas = p["equipamentos"] * p["dias"] * eq.LEITURAS_POR_DIA
    leituras = linhas * sum(p["sensores"].values())
    if leituras > TETO_LEITURAS:
        raise ValueError(f"{leituras:,} leituras excedem o teto de {TETO_LEITURAS:,}; reduza equipamentos, dias ou sensores")
    p["linhas"] = linhas
    p["leituras"] = leituras
    return p


def gerar(parametros: dict, progresso) -> dict:
    """progresso(percentual, mensagem) é chamado ao longo da geração."""
    p = validar(parametros)
    rng = np.random.default_rng(p["semente"])
    passos = p["dias"] * eq.LEITURAS_POR_DIA
    n = p["equipamentos"]
    valores = np.empty((n * passos, 3), dtype=np.float32)
    saude = np.empty(n * passos, dtype=np.float32)
    vida_util = np.empty(n * passos, dtype=np.float32)
    equip = np.repeat(np.arange(n, dtype=np.int16), passos)
    falhou = rng.random(n) < p["pct_falha"] / 100
    modos = rng.choice(p["modos_falha"], n)
    kmax = max(p["sensores"].values())
    inicio = time.time()

    for e in range(n):
        t = np.arange(passos) + int(rng.integers(0, eq.LEITURAS_POR_DIA))
        params = {k: float(v[0]) for k, v in eq.sortear_parametros(rng).items()}
        d = np.zeros(passos)
        rul = np.full(passos, VIDA_UTIL_MAXIMA_H)
        if falhou[e]:
            fim = int(rng.uniform(0.4, 1.0) * passos)
            duracao = int(rng.uniform(1, 10) * eq.LEITURAS_POR_DIA)  # degradação de 1 a 10 dias
            idx = np.arange(passos)
            antes = idx < fim
            d[antes] = np.clip((idx[antes] - (fim - duracao)) / duracao, 0, 1)
            rul[antes] = np.minimum((fim - idx[antes]) * eq.PASSO_MINUTOS / 60.0, VIDA_UTIL_MAXIMA_H)
            # depois da quebra o compressor é trocado: volta saudável (d = 0)
        modo = str(modos[e]) if falhou[e] else None

        # k sensores por variável, cada um com ruído próprio; a leitura é a média deles
        soma = np.zeros((passos, 3))
        for s in range(kmax):
            leitura = eq.valores(t, params, d, modo, rng, p["ruido"])
            leitura = _falha_de_sensor(leitura, p, rng, passos)
            for j, var in enumerate(eq.VARIAVEIS):
                if s < p["sensores"][var]:
                    soma[:, j] += leitura[:, j]
        media = soma / np.array([p["sensores"][v] for v in eq.VARIAVEIS])

        # leituras faltantes e valores absurdos
        faltante = rng.random(media.shape) < p["pct_faltantes"] / 100
        absurdo = rng.random(media.shape) < p["pct_outliers"] / 100
        media[absurdo] = np.where(rng.random(absurdo.sum()) < 0.5, media[absurdo] * rng.uniform(10, 30, absurdo.sum()), -999.0)
        media[faltante] = np.nan

        bloco = slice(e * passos, (e + 1) * passos)
        valores[bloco] = media
        saude[bloco] = 100.0 * (1.0 - d)
        vida_util[bloco] = rul
        progresso(int(90 * (e + 1) / n), f"Equipamento {e + 1} de {n} gerado")

    DIR_DADOS.mkdir(parents=True, exist_ok=True)
    temporario = DIR_DADOS / "dataset.tmp.npz"
    np.savez(temporario, valores=valores, saude=saude, vida_util=vida_util, equipamento=equip)
    temporario.rename(DIR_DADOS / "dataset.npz")
    resumo = {
        "parametros": p,
        "linhas": int(n * passos),
        "leituras": int(p["leituras"]),
        "equipamentos_com_falha": int(falhou.sum()),
        "segundos": round(time.time() - inicio, 1),
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (DIR_DADOS / "dataset.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2))
    return resumo


def _falha_de_sensor(leitura: np.ndarray, p: dict, rng, passos: int) -> np.ndarray:
    """Falhas do SENSOR (não do equipamento): deriva lenta ou valor travado."""
    if not p["falhas_sensor"] or rng.random() >= p["pct_falha_sensor"] / 100:
        return leitura
    tipo = rng.choice(p["falhas_sensor"])
    var = int(rng.integers(0, 3))
    ini = int(rng.integers(0, passos))
    if tipo == "deriva":
        rampa = np.clip((np.arange(passos) - ini) / max(1, passos - ini), 0, 1)
        leitura[:, var] *= 1 + 0.3 * rampa
    else:  # travamento
        fim = min(passos, ini + int(rng.integers(eq.LEITURAS_POR_DIA, 5 * eq.LEITURAS_POR_DIA)))
        leitura[ini:fim, var] = leitura[ini, var]
    return leitura


def amostra_para_influx(limite: int = 20000):
    """Pontos de 2 equipamentos (um que falha e um saudável) para o bucket lab."""
    # Cada dados["x"] de um .npz relê o array inteiro do disco: carrega uma vez só
    with np.load(DIR_DADOS / "dataset.npz") as dados:
        equip, saude = dados["equipamento"], dados["saude"]
        valores, vida_util = dados["valores"], dados["vida_util"]
    com_falha = np.unique(equip[saude < 100])
    saudaveis = np.setdiff1d(np.unique(equip), com_falha)
    escolhidos = [int(x) for x in list(com_falha[:1]) + list(saudaveis[:1])]
    for e in escolhidos:
        idx = np.flatnonzero(equip == e)
        passo = max(1, len(idx) // (limite // max(1, len(escolhidos))))
        for i, j in enumerate(idx[::passo]):
            yield e, i * passo, valores[j].tolist(), float(saude[j]), float(vida_util[j])
