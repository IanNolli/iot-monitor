"""Cálculo das features (variáveis de entrada) dos modelos de regressão.

ÚNICO código usado tanto no treino (serviço lab) quanto na inferência em tempo real
(serviço inferencia), para não haver divergência entre os dois.

Cada janela contém as JANELA últimas leituras do equipamento (só o passado):
array (N, JANELA, 3) com vibração, corrente e temperatura.
"""

import numpy as np

from .equipamento import PASSO_MINUTOS, VARIAVEIS

JANELA = 24  # 24 leituras = 2 horas de operação simulada

# Faixa física plausível; fora dela a leitura é tratada como valor absurdo (outlier)
FAIXAS = np.array([[0.0, 50.0], [0.0, 20.0], [-10.0, 150.0]])

ESTATISTICAS = ("media", "desvio", "minimo", "maximo", "ultimo", "tendencia")
NOMES = [f"{var}_{est}" for var in VARIAVEIS for est in ESTATISTICAS]


def limpar(janelas: np.ndarray) -> np.ndarray:
    """Troca valores fora da faixa física por NaN (leituras faltantes já chegam como NaN)."""
    x = np.array(janelas, dtype=np.float64, copy=True)
    fora = (x < FAIXAS[:, 0]) | (x > FAIXAS[:, 1])
    x[fora] = np.nan
    return x


def calcular(janelas: np.ndarray) -> np.ndarray:
    """(N, JANELA, 3) -> (N, 18). Os modelos aceitam NaN nas features."""
    x = limpar(janelas)
    n, w, _ = x.shape
    with np.errstate(invalid="ignore"), warnings_silenciados():
        media = np.nanmean(x, axis=1)
        desvio = np.nanstd(x, axis=1)
        minimo = np.nanmin(x, axis=1)
        maximo = np.nanmax(x, axis=1)
        ultimo = _ultimo_valido(x)
        tendencia = _tendencia_por_hora(x)
    blocos = [media, desvio, minimo, maximo, ultimo, tendencia]
    # Reorganiza para a ordem de NOMES: variável por variável
    return np.stack(blocos, axis=2).reshape(n, -1)


def _ultimo_valido(x: np.ndarray) -> np.ndarray:
    validos = ~np.isnan(x)
    # índice da última posição válida em cada janela/variável
    idx = x.shape[1] - 1 - np.argmax(validos[:, ::-1, :], axis=1)
    ultimo = np.take_along_axis(x, idx[:, None, :], axis=1)[:, 0, :]
    ultimo[~validos.any(axis=1)] = np.nan
    return ultimo


def _tendencia_por_hora(x: np.ndarray) -> np.ndarray:
    """Inclinação da reta (mínimos quadrados) ignorando NaN, em unidades por hora."""
    t = np.arange(x.shape[1], dtype=np.float64)[None, :, None] * PASSO_MINUTOS / 60.0
    validos = ~np.isnan(x)
    cont = validos.sum(axis=1)
    t_val = np.where(validos, t, 0.0)
    x_val = np.where(validos, x, 0.0)
    media_t = t_val.sum(axis=1) / np.maximum(cont, 1)
    media_x = x_val.sum(axis=1) / np.maximum(cont, 1)
    cov = (np.where(validos, (t - media_t[:, None, :]) * (x - media_x[:, None, :]), 0.0)).sum(axis=1)
    var = (np.where(validos, (t - media_t[:, None, :]) ** 2, 0.0)).sum(axis=1)
    inclinacao = cov / np.where(var > 0, var, np.nan)
    inclinacao[cont < 3] = np.nan
    return inclinacao


class warnings_silenciados:
    """nanmean de janela totalmente vazia gera aviso; o resultado NaN é o esperado."""

    def __enter__(self):
        import warnings

        self._ctx = warnings.catch_warnings()
        self._ctx.__enter__()
        warnings.simplefilter("ignore", category=RuntimeWarning)

    def __exit__(self, *exc):
        return self._ctx.__exit__(*exc)
