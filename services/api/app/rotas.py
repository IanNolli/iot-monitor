"""Rotas REST principais: login, dispositivos, comandos, telemetria, regras, alertas e auditoria."""

import time

from aiot_common import mensagens
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import consumidores, db, estado, influx, seguranca

rotas = APIRouter(prefix="/api")
qualquer = seguranca.exigir("visualizador")
operador = seguranca.exigir("operador")
admin = seguranca.exigir("administrador")


# ---------- autenticação ----------
class Login(BaseModel):
    login: str = Field(max_length=60)
    senha: str = Field(max_length=200)


@rotas.post("/auth/login", tags=["autenticação"], summary="Login com usuário e senha; devolve um JWT")
async def login(dados: Login, request: Request):
    return await seguranca.autenticar(dados.login.strip().lower(), dados.senha, request)


@rotas.get("/auth/eu", tags=["autenticação"], summary="Usuário do token atual")
async def eu(usuario: dict = Depends(qualquer)):
    return usuario


@rotas.post("/ws/ticket", tags=["tempo real"], summary="Ticket curto e de uso único para abrir o WebSocket")
async def ticket(usuario: dict = Depends(qualquer)):
    return {"ticket": seguranca.criar_ticket(usuario), "expira_em_s": 30}


# ---------- dispositivos ----------
class Dispositivo(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{2,40}$")
    nome: str = Field(min_length=2, max_length=80)
    classe: str = Field(pattern="^(sensor|atuador|equipamento)$")
    zona: str = Field(pattern=r"^[a-z0-9-]{2,30}$")
    grandeza: str = Field(max_length=60)
    unidade: str = Field(default="", max_length=10)
    faixa_min: float | None = None
    faixa_max: float | None = None
    controlavel: bool = False
    ativo: bool = True


@rotas.get("/dispositivos", tags=["dispositivos"], summary="Lista os dispositivos cadastrados")
async def listar_dispositivos(_: dict = Depends(qualquer)):
    return [dict(r) for r in await db.pool.fetch("SELECT * FROM dispositivos ORDER BY classe, id")]


@rotas.post("/dispositivos", tags=["dispositivos"], status_code=201, summary="Cadastra um dispositivo (administrador)")
async def criar_dispositivo(d: Dispositivo, usuario: dict = Depends(admin)):
    try:
        await db.pool.execute(
            """INSERT INTO dispositivos (id, nome, classe, zona, grandeza, unidade, faixa_min, faixa_max, controlavel, ativo)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""", *d.model_dump().values())
    except Exception as erro:
        if "duplicate key" in str(erro):
            raise HTTPException(409, f"Já existe um dispositivo com o id {d.id}.")
        raise
    await db.auditar(usuario["login"], "dispositivo_criado", d.model_dump())
    return d


@rotas.put("/dispositivos/{dispositivo_id}", tags=["dispositivos"], summary="Altera um dispositivo (administrador)")
async def alterar_dispositivo(dispositivo_id: str, d: Dispositivo, usuario: dict = Depends(admin)):
    if d.id != dispositivo_id:
        raise HTTPException(400, "O id não pode ser alterado.")
    resultado = await db.pool.execute(
        """UPDATE dispositivos SET nome=$2, classe=$3, zona=$4, grandeza=$5, unidade=$6, faixa_min=$7, faixa_max=$8,
           controlavel=$9, ativo=$10 WHERE id=$1""", *d.model_dump().values())
    if resultado.endswith(" 0"):
        raise HTTPException(404, "Dispositivo não encontrado.")
    await db.auditar(usuario["login"], "dispositivo_alterado", d.model_dump())
    return d


@rotas.delete("/dispositivos/{dispositivo_id}", tags=["dispositivos"], status_code=204, summary="Remove um dispositivo (administrador)")
async def remover_dispositivo(dispositivo_id: str, usuario: dict = Depends(admin)):
    resultado = await db.pool.execute("DELETE FROM dispositivos WHERE id = $1", dispositivo_id)
    if resultado.endswith(" 0"):
        raise HTTPException(404, "Dispositivo não encontrado.")
    await consumidores.recarregar_regras()
    await db.auditar(usuario["login"], "dispositivo_removido", {"id": dispositivo_id})


class Comando(BaseModel):
    ligado: bool


@rotas.post("/dispositivos/{dispositivo_id}/comando", tags=["dispositivos"], summary="Liga ou desliga um atuador (operador)")
async def comandar(dispositivo_id: str, comando: Comando, usuario: dict = Depends(operador)):
    d = await db.pool.fetchrow("SELECT * FROM dispositivos WHERE id = $1", dispositivo_id)
    if not d or d["classe"] != "atuador":
        raise HTTPException(404, "Atuador não encontrado.")
    if not d["controlavel"]:
        raise HTTPException(409, "Este atuador é controlado por regra automática.")
    conteudo = {"ligado": comando.ligado, "origem": "web", "usuario": usuario["login"]}
    await consumidores.publicar(f"comando.{dispositivo_id}", mensagens.criar("comando", conteudo, dispositivo_id))
    await db.auditar(usuario["login"], "comando", {"dispositivo": dispositivo_id, "ligado": comando.ligado})
    return {"enviado": True, **conteudo}


class ComandoSimulador(BaseModel):
    acao: str = Field(pattern="^(injetar_falha|reparar)$")
    modo: str = Field(default="rolamento", pattern="^(rolamento|entupimento|superaquecimento|desbalanceamento)$")


@rotas.post("/simulador/comando", tags=["dispositivos"], summary="Injeta falha ou repara o compressor no simulador (operador)")
async def comandar_simulador(c: ComandoSimulador, usuario: dict = Depends(operador)):
    await consumidores.publicar("comando.simulador", mensagens.criar("comando", c.model_dump(), "simulador"))
    await db.auditar(usuario["login"], "comando_simulador", c.model_dump())
    return {"enviado": True}


# ---------- telemetria ----------
@rotas.get("/telemetria/atual", tags=["telemetria"], summary="Última leitura de cada dispositivo")
async def telemetria_atual(_: dict = Depends(qualquer)):
    return {"leituras": estado.ultimas_leituras, "previsoes": estado.ultimas_previsoes,
            "segundos_desde_ultima": round(time.time() - estado.ultima_telemetria_em, 1) if estado.ultima_telemetria_em else None}


@rotas.get("/telemetria/historico", tags=["telemetria"], summary="Histórico agregado de um dispositivo no InfluxDB")
async def telemetria_historico(dispositivo: str, campos: str = "valor", minutos: int = 60, _: dict = Depends(qualquer)):
    try:
        return await influx.serie("telemetria", dispositivo, campos.split(","), minutos)
    except ValueError as erro:
        raise HTTPException(400, str(erro))


# ---------- regras, alertas, auditoria ----------
class Regra(BaseModel):
    limite_liga: float
    limite_desliga: float
    ativa: bool = True


@rotas.get("/regras", tags=["regras"], summary="Regras de negócio dos atuadores automáticos")
async def listar_regras(_: dict = Depends(qualquer)):
    return [dict(r) for r in await db.pool.fetch("SELECT * FROM regras ORDER BY id")]


@rotas.put("/regras/{regra_id}", tags=["regras"], summary="Altera limites de uma regra (administrador)")
async def alterar_regra(regra_id: int, r: Regra, usuario: dict = Depends(admin)):
    if r.limite_desliga >= r.limite_liga:
        raise HTTPException(400, "O limite para desligar deve ser menor que o limite para ligar.")
    await db.pool.execute("UPDATE regras SET limite_liga=$2, limite_desliga=$3, ativa=$4 WHERE id=$1", regra_id, r.limite_liga, r.limite_desliga, r.ativa)
    await consumidores.recarregar_regras()
    await db.auditar(usuario["login"], "regra_alterada", {"id": regra_id, **r.model_dump()})
    return r


@rotas.get("/alertas", tags=["alertas"], summary="Alertas da IA (abertos primeiro)")
async def listar_alertas(limite: int = 30, _: dict = Depends(qualquer)):
    return [dict(r) for r in await db.pool.fetch(
        "SELECT * FROM alertas ORDER BY (fechado_em IS NULL) DESC, aberto_em DESC LIMIT $1", min(limite, 200))]


@rotas.get("/auditoria", tags=["auditoria"], summary="Log de auditoria (administrador)")
async def auditoria(limite: int = 100, _: dict = Depends(admin)):
    return [dict(r) for r in await db.pool.fetch("SELECT * FROM auditoria ORDER BY instante DESC LIMIT $1", min(limite, 500))]


@rotas.get("/infra", tags=["infraestrutura"], summary="Links das interfaces de administração (somente 127.0.0.1)")
async def infra(_: dict = Depends(qualquer)):
    return [
        {"nome": "RabbitMQ (gerenciamento)", "url": "http://127.0.0.1:15672", "usuario": "admin"},
        {"nome": "InfluxDB", "url": "http://127.0.0.1:8086", "usuario": "admin"},
        {"nome": "pgAdmin (PostgreSQL)", "url": "http://127.0.0.1:5050", "usuario": "pgadmin@example.com"},
        {"nome": "Documentação da API (Swagger)", "url": "/api/docs", "usuario": None},
    ]
