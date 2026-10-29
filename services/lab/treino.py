"""Treino dos 2 modelos de regressão com os dados sintéticos.

- vida_util: tempo até a falha, em horas (limitado a 240 h)
- saude:     índice de saúde de 0 a 100

Divisão treino/validação/teste POR EQUIPAMENTO (nunca por linha). As features vêm de
aiot_common.features, o mesmo código usado na inferência em tempo real. Cada modelo é
comparado com uma base simples (prever sempre a média do treino) e só entra em uso se
vencer a base nas duas métricas de erro.
"""

import json
import time
from pathlib import Path

import joblib
import numpy as np
from aiot_common import features
from numpy.lib.stride_tricks import sliding_window_view
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

DIR_DADOS = Path("/dados")
DIR_MODELOS = Path("/modelos")
ALVOS = {"vida_util": "Vida útil restante (h, até 240)", "saude": "Índice de saúde (0–100)"}


def _janelas(valores, equip, ids_equip, max_amostras, rng):
    """Seleciona linhas dos equipamentos pedidos e monta janelas só com o passado."""
    blocos_x, blocos_idx = [], []
    for e in ids_equip:
        idx = np.flatnonzero(equip == e)
        if len(idx) < features.JANELA:
            continue
        vistas = sliding_window_view(valores[idx], features.JANELA, axis=0)  # (n-J+1, 3, J)
        blocos_x.append(vistas)
        blocos_idx.append(idx[features.JANELA - 1:])  # a janela termina na linha atual
    total = sum(len(b) for b in blocos_idx)
    escolha = np.sort(rng.choice(total, size=min(max_amostras, total), replace=False))
    deslocamentos = np.cumsum([0] + [len(b) for b in blocos_idx])
    x_lista, idx_lista = [], []
    for k, (vistas, idx) in enumerate(zip(blocos_x, blocos_idx)):
        locais = escolha[(escolha >= deslocamentos[k]) & (escolha < deslocamentos[k + 1])] - deslocamentos[k]
        if len(locais):
            x_lista.append(np.transpose(vistas[locais], (0, 2, 1)))  # -> (m, J, 3)
            idx_lista.append(idx[locais])
    janelas = np.concatenate(x_lista)
    x = np.concatenate([features.calcular(janelas[i:i + 50000]) for i in range(0, len(janelas), 50000)])
    return x, np.concatenate(idx_lista)


def _metricas(y, previsto) -> dict:
    return {
        "mae": round(float(mean_absolute_error(y, previsto)), 3),
        "rmse": round(float(np.sqrt(mean_squared_error(y, previsto))), 3),
        "r2": round(float(r2_score(y, previsto)), 4),
    }


def treinar(parametros: dict, progresso) -> dict:
    inicio = time.time()
    arquivo = DIR_DADOS / "dataset.npz"
    if not arquivo.exists():
        raise RuntimeError("Nenhum dataset gerado. Gere os dados no Laboratório primeiro.")
    amostras = int(np.clip(parametros.get("amostras_treino", 200_000), 10_000, 1_000_000))
    rng = np.random.default_rng(int(parametros.get("semente", 7)))

    progresso(5, "Carregando o dataset")
    with np.load(arquivo) as npz:  # carrega cada array uma única vez
        dados = {nome: npz[nome] for nome in npz.files}
    valores, equip = dados["valores"], dados["equipamento"]
    ids = rng.permutation(np.unique(equip))
    n_tr, n_va = int(0.7 * len(ids)), int(0.15 * len(ids))
    grupos = {"treino": ids[:n_tr], "validacao": ids[n_tr:n_tr + n_va], "teste": ids[n_tr + n_va:]}
    if min(len(g) for g in grupos.values()) == 0:
        raise RuntimeError("São necessários pelo menos 7 equipamentos para dividir treino, validação e teste")

    progresso(15, "Calculando features (janelas do passado)")
    conjuntos = {}
    for nome, ids_grupo in grupos.items():
        limite = amostras if nome == "treino" else max(amostras // 4, 10_000)
        conjuntos[nome] = _janelas(valores, equip, ids_grupo, limite, rng)

    versao = 1 + max([int(p.name[1:]) for p in DIR_MODELOS.glob("v*") if p.name[1:].isdigit()] or [0])
    destino = DIR_MODELOS / f"v{versao}"
    destino.mkdir(parents=True, exist_ok=True)
    resultado = {"versao": versao, "modelos": {}, "amostras_treino": int(len(conjuntos["treino"][1])),
                 "equipamentos": {k: int(len(v)) for k, v in grupos.items()}}

    for i, (alvo, descricao) in enumerate(ALVOS.items()):
        progresso(30 + 30 * i, f"Treinando modelo de {descricao.lower()}")
        y = {nome: dados[alvo][idx] for nome, (_, idx) in conjuntos.items()}
        x = {nome: xx for nome, (xx, _) in conjuntos.items()}
        modelo = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06, max_leaf_nodes=15,
                                               min_samples_leaf=200, l2_regularization=1.0, random_state=0)
        modelo.fit(x["treino"], y["treino"])
        base = DummyRegressor(strategy="mean").fit(x["treino"], y["treino"])
        prev_teste = modelo.predict(x["teste"])
        m_modelo = _metricas(y["teste"], prev_teste)
        m_base = _metricas(y["teste"], base.predict(x["teste"]))
        m_val = _metricas(y["validacao"], modelo.predict(x["validacao"]))

        progresso(45 + 30 * i, "Calculando a importância dos atributos")
        amostra = rng.choice(len(y["teste"]), size=min(3000, len(y["teste"])), replace=False)
        imp = permutation_importance(modelo, x["teste"][amostra], y["teste"][amostra], n_repeats=3, random_state=0,
                                     scoring="neg_mean_absolute_error")
        importancia = sorted(
            ({"atributo": nome, "importancia": round(float(v), 4)} for nome, v in zip(features.NOMES, imp.importances_mean)),
            key=lambda item: -item["importancia"],
        )[:10]
        pontos = rng.choice(len(y["teste"]), size=min(400, len(y["teste"])), replace=False)
        resultado["modelos"][alvo] = {
            "descricao": descricao,
            "algoritmo": "HistGradientBoostingRegressor",
            "teste": m_modelo,
            "validacao": m_val,
            "base_media": m_base,
            "vence_base": m_modelo["mae"] < m_base["mae"] and m_modelo["rmse"] < m_base["rmse"],
            "importancia": importancia,
            "previsto_vs_real": [[round(float(y["teste"][j]), 2), round(float(prev_teste[j]), 2)] for j in pontos],
        }
        joblib.dump({"modelo": modelo, "features": features.NOMES, "alvo": alvo, "versao": versao}, destino / f"{alvo}.joblib")

    resultado["em_uso"] = all(m["vence_base"] for m in resultado["modelos"].values())
    resultado["segundos"] = round(time.time() - inicio, 1)
    (destino / "metricas.json").write_text(json.dumps(resultado, ensure_ascii=False))
    if resultado["em_uso"]:
        temporario = DIR_MODELOS / "atual.tmp.json"
        temporario.write_text(json.dumps({"versao": versao, "diretorio": str(destino)}))
        temporario.rename(DIR_MODELOS / "atual.json")  # troca atômica: a inferência lê a nova versão
    progresso(100, "Treino concluído")
    return resultado
