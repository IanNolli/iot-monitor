"""Rotas de IA e mensageria: laboratório, treino, insights, assistente e página Mensageria."""

import json
import time
import uuid
from collections import defaultdict, deque

import aio_pika
import httpx
from aiot_common import mensagens
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import config, consumidores, db, estado, influx, seguranca

rotas = APIRouter(prefix="/api")
qualquer = seguranca.exigir("visualizador")
admin = seguranca.exigir("administrador")


# ---------- laboratório de dados ----------
class Sensores(BaseModel):
    vibracao: int = Field(1, ge=1, le=3)
    corrente: int = Field(1, ge=1, le=3)
    temperatura: int = Field(1, ge=1, le=3)


class ParametrosGeracao(BaseModel):
    equipamentos: int = Field(60, ge=1, le=500)
    dias: int = Field(60, ge=1, le=365)
    sensores: Sensores = Sensores()
    pct_falha: float = Field(50, ge=0, le=100)
    modos_falha: list[str] = ["rolamento", "entupimento", "superaquecimento", "desbalanceamento"]
    falhas_sensor: list[str] = ["deriva", "travamento"]
    pct_falha_sensor: float = Field(10, ge=0, le=100)
    ruido: float = Field(1.0, ge=0, le=3)
    pct_faltantes: float = Field(1.0, ge=0, le=20)
    pct_outliers: float = Field(0.5, ge=0, le=10)
    semente: int = 42


class ParametrosTreino(BaseModel):
    amostras_treino: int = Field(200_000, ge=10_000, le=1_000_000)
    semente: int = 7


async def _criar_job(tipo: str, routing_key: str, parametros: dict, usuario: dict) -> dict:
    job_id = str(uuid.uuid4())
    await db.pool.execute("INSERT INTO jobs (id, tipo, parametros, criado_por, mensagem) VALUES ($1::uuid, $2, $3, $4, 'Na fila')",
                          job_id, tipo, parametros, usuario["login"])
    await consumidores.publicar(routing_key, mensagens.criar("job", {"job_id": job_id, "tipo": tipo, "parametros": parametros}))
    await db.auditar(usuario["login"], f"job_{tipo}", {"job_id": job_id, "parametros": parametros})
    return {"job_id": job_id, "status": "na_fila"}


@rotas.post("/lab/gerar", tags=["laboratório"], status_code=202, summary="Inicia a geração de dados sintéticos (administrador)")
async def gerar(p: ParametrosGeracao, usuario: dict = Depends(admin)):
    linhas = p.equipamentos * p.dias * 288
    leituras = linhas * (p.sensores.vibracao + p.sensores.corrente + p.sensores.temperatura)
    if leituras > 20_000_000:
        raise HTTPException(400, f"{leituras:,} leituras excedem o teto de 20.000.000. Reduza equipamentos, dias ou sensores.".replace(",", "."))
    return await _criar_job("geracao", "job.lab", p.model_dump(), usuario)


@rotas.post("/modelos/treinar", tags=["treinamento"], status_code=202, summary="Inicia o treino dos modelos (administrador)")
async def treinar(p: ParametrosTreino, usuario: dict = Depends(admin)):
    return await _criar_job("treino", "job.treino", p.model_dump(), usuario)


@rotas.get("/lab/jobs", tags=["laboratório"], summary="Jobs de geração e treino")
async def jobs(tipo: str | None = None, _: dict = Depends(qualquer)):
    linhas = await db.pool.fetch("SELECT * FROM jobs WHERE ($1::text IS NULL OR tipo = $1) ORDER BY criado_em DESC LIMIT 20", tipo)
    return [dict(r) for r in linhas]


@rotas.get("/lab/resumo", tags=["laboratório"], summary="Último dataset gerado e pontos no bucket lab")
async def resumo_lab(_: dict = Depends(qualquer)):
    ultimo = await db.pool.fetchrow("SELECT resultado FROM jobs WHERE tipo='geracao' AND status='concluido' ORDER BY atualizado_em DESC LIMIT 1")
    return {"dataset": ultimo["resultado"] if ultimo else None, "pontos_bucket_lab": await influx.contar_pontos("lab")}


@rotas.get("/lab/amostra", tags=["laboratório"], summary="Amostra dos dados sintéticos (bucket lab)")
async def amostra_lab(equipamento: str | None = None, _: dict = Depends(qualquer)):
    try:
        equipamentos = await influx.valores_tag("lab", "equipamento")
        if not equipamentos:
            return {"equipamentos": [], "equipamento": None, "serie": {}}
        padrao = next((e for e in equipamentos if e.endswith("com-falha")), equipamentos[0])
        escolhido = equipamento if equipamento in equipamentos else padrao
        # período = dias simulados do último dataset (a amostra termina "agora" e volta no tempo)
        ultimo = await db.pool.fetchval("SELECT resultado FROM jobs WHERE tipo='geracao' AND status='concluido' "
                                        "ORDER BY atualizado_em DESC LIMIT 1")
        dias = int((ultimo or {}).get("parametros", {}).get("dias", 60)) + 1
        serie = await influx.serie("sintetico", escolhido, ["vibracao", "corrente", "temperatura", "saude"], 60 * 24 * dias,
                                   bucket="lab", tag="equipamento", pontos=300)
        return {"equipamentos": equipamentos, "equipamento": escolhido, "serie": serie}
    except Exception:
        return {"equipamentos": [], "equipamento": None, "serie": {}}


@rotas.get("/modelos", tags=["treinamento"], summary="Versões treinadas, métricas e versão em uso")
async def modelos(_: dict = Depends(qualquer)):
    return [dict(r) for r in await db.pool.fetch("SELECT * FROM modelos ORDER BY versao DESC LIMIT 10")]


# ---------- insights ----------
@rotas.get("/insights", tags=["insights"], summary="Saúde, vida útil, tendência e alertas por equipamento")
async def insights(_: dict = Depends(qualquer)):
    equipamentos = await db.pool.fetch("SELECT id, nome FROM dispositivos WHERE classe = 'equipamento' ORDER BY id")
    em_uso = await db.pool.fetchrow("SELECT versao, metricas FROM modelos WHERE em_uso")
    saida = []
    for e in equipamentos:
        alertas = await db.pool.fetch("SELECT * FROM alertas WHERE dispositivo_id = $1 AND fechado_em IS NULL", e["id"])
        try:
            historico = await influx.serie("previsao", e["id"], ["saude", "vida_util_h"], 30)
        except Exception:
            historico = {}
        saida.append({"id": e["id"], "nome": e["nome"], "previsao": estado.ultimas_previsoes.get(e["id"]),
                      "alertas": [dict(a) for a in alertas], "historico": historico})
    return {"modelo_em_uso": em_uso["versao"] if em_uso else None, "equipamentos": saida}


# ---------- mensageria ----------
@rotas.get("/mensageria", tags=["mensageria"], summary="Filas, taxas, consumidores, últimas mensagens e DLQ")
async def mensageria(_: dict = Depends(qualquer)):
    async with httpx.AsyncClient(base_url=config.RABBIT_MGMT, auth=("api", config.RABBIT_SENHA), timeout=5) as c:
        filas = (await c.get("/queues/aiot")).json()
        consumidores_ = (await c.get("/consumers/aiot")).json()
        dlq = (await c.post("/queues/aiot/aiot.dlq/get",
                            json={"count": 10, "ackmode": "ack_requeue_true", "encoding": "auto", "truncate": 2000})).json()
        visao = (await c.get("/overview")).json()

    def taxa(item: dict, chave: str) -> float:
        return round(item.get("message_stats", {}).get(f"{chave}_details", {}).get("rate", 0.0), 2)

    return {
        "filas": [{
            "nome": f["name"], "mensagens": f.get("messages", 0), "prontas": f.get("messages_ready", 0),
            "nao_confirmadas": f.get("messages_unacknowledged", 0), "consumidores": f.get("consumers", 0),
            "entrada_por_s": taxa(f, "publish"), "entrega_por_s": taxa(f, "deliver_get"),
        } for f in filas],
        "consumidores": [{"fila": c["queue"]["name"], "conexao": c["channel_details"].get("connection_name", ""),
                          "usuario": c["channel_details"].get("user", "")} for c in consumidores_],
        "taxas_globais": {"publicacao_por_s": taxa(visao, "publish"), "entrega_por_s": taxa(visao, "deliver_get")},
        "recentes": list(estado.mensagens_recentes)[:20],
        "dlq": [{"motivo": (d.get("properties", {}).get("headers") or {}).get("motivo")
                 or ((d.get("properties", {}).get("headers") or {}).get("x-death") or [{}])[0].get("reason"),
                 "origem": d.get("routing_key"), "corpo": d.get("payload")} for d in dlq] if isinstance(dlq, list) else [],
    }


@rotas.post("/mensageria/teste-dlq", tags=["mensageria"], summary="Publica uma mensagem fora do formato para demonstrar a DLQ (administrador)")
async def teste_dlq(usuario: dict = Depends(admin)):
    # Corpo sem o envelope obrigatório: o gravador rejeita sem requeue e o RabbitMQ a move para aiot.dlq
    await consumidores.exchange.publish(
        aio_pika.Message(body=b'{"teste": "mensagem fora do formato unico"}', content_type="application/json"),
        routing_key="telemetria.teste.sensor.dlq-demo",
    )
    await db.auditar(usuario["login"], "teste_dlq", {})
    return {"enviado": True}


# ---------- assistente com LLM local ----------
_perguntas: dict[str, deque] = defaultdict(deque)

ARQUITETURA = """Arquitetura: o simulador (Python) publica telemetria no Mosquitto via MQTT; o gateway repassa para o
RabbitMQ (exchange topic aiot.eventos). Dali: o gravador salva no InfluxDB (séries temporais), a inferência aplica os
modelos de regressão (scikit-learn) e publica previsões e alertas, a API FastAPI aplica regras de negócio, guarda
cadastros, regras, alertas e auditoria no PostgreSQL e entrega tudo ao navegador por WebSocket. Comandos fazem o caminho
inverso: dashboard -> API -> RabbitMQ -> gateway -> MQTT -> simulador. O laboratório gera dados sintéticos massivos e
treina os modelos em segundo plano por filas do RabbitMQ. Tudo roda em Docker Compose; este assistente usa um LLM local
(Ollama), sem nuvem."""


async def _contexto() -> str:
    linhas = []
    for d, m in estado.ultimas_leituras.items():
        c = {k: v for k, v in m["conteudo"].items() if k not in ("zona", "classe")}
        linhas.append(f"- {d}: {json.dumps(c, ensure_ascii=False)}")
    previsoes = [f"- {d}: saúde {p['conteudo']['saude']}/100, vida útil restante ~{p['conteudo']['vida_util_h']} h, "
                 f"tendência {p['conteudo']['tendencia_saude_h']} pontos/h, nível {p['conteudo']['nivel']}"
                 for d, p in estado.ultimas_previsoes.items()]
    alertas = await db.pool.fetch("SELECT dispositivo_id, nivel, mensagem, aberto_em FROM alertas WHERE fechado_em IS NULL")
    modelo = await db.pool.fetchrow("SELECT versao, metricas FROM modelos WHERE em_uso")
    regras = await db.pool.fetch("SELECT nome, limite_liga, limite_desliga FROM regras WHERE ativa")
    metricas = "nenhum modelo treinado ainda"
    if modelo:
        partes = []
        for alvo, m in modelo["metricas"]["modelos"].items():
            partes.append(f"{m['descricao']}: MAE {m['teste']['mae']}, RMSE {m['teste']['rmse']}, R² {m['teste']['r2']} "
                          f"(base que prevê a média: MAE {m['base_media']['mae']}, R² {m['base_media']['r2']})")
        metricas = f"versão {modelo['versao']} em uso. " + "; ".join(partes)
    return "\n".join([
        "Leituras atuais:", *(linhas or ["- sem dados (simulador parado?)"]),
        "Previsões da IA:", *(previsoes or ["- sem previsões (modelo não treinado ou sem telemetria)"]),
        "Alertas abertos:", *([f"- {a['dispositivo_id']} ({a['nivel']}): {a['mensagem']}" for a in alertas] or ["- nenhum"]),
        f"Modelos: {metricas}",
        "Regras automáticas: " + "; ".join(f"{r['nome']} (liga acima de {r['limite_liga']}, desliga abaixo de {r['limite_desliga']})" for r in regras),
        "Observação: o simulador é acelerado (cada leitura = 5 min simulados), então as horas de vida útil são horas simuladas.",
        ARQUITETURA,
    ])


class Pergunta(BaseModel):
    pergunta: str = Field(min_length=2, max_length=1000)


@rotas.get("/assistente/status", tags=["assistente"], summary="Se o modelo local está baixado e carregado")
async def status_assistente(_: dict = Depends(qualquer)):
    try:
        async with httpx.AsyncClient(base_url=config.OLLAMA_URL, timeout=3) as c:
            baixados = [m["name"] for m in (await c.get("/api/tags")).json().get("models", [])]
            carregados = [m["name"] for m in (await c.get("/api/ps")).json().get("models", [])]
    except (httpx.HTTPError, ValueError):  # fora do ar ou resposta que não é JSON
        return {"modelo": config.OLLAMA_MODELO, "estado": "indisponivel"}
    estado_ = "pronto" if config.OLLAMA_MODELO in carregados else ("carregando" if config.OLLAMA_MODELO in baixados else "baixando")
    return {"modelo": config.OLLAMA_MODELO, "estado": estado_}


@rotas.post("/assistente/perguntar", tags=["assistente"], summary="Pergunta ao assistente; resposta em streaming")
async def perguntar(p: Pergunta, usuario: dict = Depends(qualquer)):
    limite = int(await db.pool.fetchval("SELECT valor FROM configuracoes WHERE chave = 'assistente_limite_por_minuto'") or 5)
    janela = _perguntas[usuario["login"]]
    agora = time.time()
    while janela and agora - janela[0] > 60:
        janela.popleft()
    if len(janela) >= limite:
        raise HTTPException(429, f"Limite de {limite} perguntas por minuto atingido. Aguarde um pouco.")
    janela.append(agora)
    await db.auditar(usuario["login"], "pergunta_assistente", {"pergunta": p.pergunta[:500]})

    sistema = ("Você é o assistente da aplicação Smart Home AIoT. Responda sempre em português do Brasil, de forma curta e "
               "clara, usando SOMENTE os dados do contexto abaixo. Se a informação não estiver no contexto, diga que não sabe. "
               "Explique alertas e o que fazer de forma prática.\n"
               "O equipamento monitorado é o compressor da geladeira (comp-geladeira). Valores típicos de um compressor "
               "saudável: vibração ~2 mm/s, corrente ~1,2 A, temperatura ~45 °C. Vibração alta indica rolamento gasto ou "
               "desbalanceamento; temperatura alta indica superaquecimento ou entupimento; corrente alta indica esforço do "
               "motor. Recomende ações sobre o compressor (inspeção técnica, troca de rolamento, limpeza do condensador, "
               "verificação de ventilação), comparando as leituras atuais com esses valores.\n\nCONTEXTO ATUAL:\n" + await _contexto())
    corpo = {"model": config.OLLAMA_MODELO, "stream": True, "keep_alive": -1, "options": {"temperature": 0.2, "num_ctx": 4096},
             "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": p.pergunta}]}

    async def gerar():
        try:
            async with httpx.AsyncClient(base_url=config.OLLAMA_URL, timeout=httpx.Timeout(300, connect=5)) as c:
                async with c.stream("POST", "/api/chat", json=corpo) as r:
                    if r.status_code != 200:
                        yield "O modelo local ainda não está disponível. Aguarde o download terminar e tente de novo."
                        return
                    async for linha in r.aiter_lines():
                        if linha:
                            parte = json.loads(linha)
                            if parte.get("message", {}).get("content"):
                                yield parte["message"]["content"]
        except httpx.HTTPError:
            yield "Não foi possível falar com o LLM local (serviço ollama)."

    return StreamingResponse(gerar(), media_type="text/plain; charset=utf-8", headers={"X-Accel-Buffering": "no"})
