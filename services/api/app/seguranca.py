"""Login com JWT, papéis, limite de tentativas e tickets de uso único para o WebSocket."""

import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config, db

NIVEL = {"visualizador": 0, "operador": 1, "administrador": 2}
_bearer = HTTPBearer(auto_error=False)

# Limite por IP (além do bloqueio por usuário no banco): 20 tentativas a cada 5 minutos
_tentativas_ip: dict[str, deque] = defaultdict(deque)
# Tickets do WebSocket: ticket -> (usuario, papel, expira_em)
_tickets: dict[str, tuple[str, str, float]] = {}


def _ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


async def autenticar(login: str, senha: str, request: Request) -> dict:
    ip = _ip(request)
    janela = _tentativas_ip[ip]
    agora = time.time()
    while janela and agora - janela[0] > 300:
        janela.popleft()
    if len(janela) >= 20:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Muitas tentativas deste endereço. Aguarde alguns minutos.")
    janela.append(agora)

    usuario = await db.pool.fetchrow("SELECT * FROM usuarios WHERE login = $1", login)
    if usuario and usuario["bloqueado_ate"] and usuario["bloqueado_ate"] > datetime.now(timezone.utc):
        await db.auditar(login, "login_bloqueado", {"ip": ip})
        raise HTTPException(status.HTTP_423_LOCKED, "Usuário bloqueado temporariamente por excesso de tentativas.")
    if not usuario or not bcrypt.checkpw(senha.encode(), usuario["senha_hash"].encode()):
        if usuario:
            falhas = usuario["falhas_login"] + 1
            bloqueio = datetime.now(timezone.utc) + timedelta(minutes=config.LOGIN_BLOQUEIO_MIN) if falhas >= config.LOGIN_MAX_FALHAS else None
            await db.pool.execute("UPDATE usuarios SET falhas_login = $2, bloqueado_ate = $3 WHERE id = $1",
                                  usuario["id"], 0 if bloqueio else falhas, bloqueio)
        await db.auditar(login, "login_falhou", {"ip": ip})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário ou senha inválidos.")

    await db.pool.execute("UPDATE usuarios SET falhas_login = 0, bloqueado_ate = NULL WHERE id = $1", usuario["id"])
    await db.auditar(login, "login", {"ip": ip})
    expira = datetime.now(timezone.utc) + timedelta(hours=config.JWT_HORAS)
    token = jwt.encode({"sub": login, "papel": usuario["papel"], "nome": usuario["nome"], "exp": expira},
                       config.JWT_SEGREDO, algorithm="HS256")
    return {"token": token, "usuario": {"login": login, "nome": usuario["nome"], "papel": usuario["papel"]}}


async def usuario_atual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Faça login para continuar.")
    try:
        dados = jwt.decode(cred.credentials, config.JWT_SEGREDO, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada ou inválida. Faça login novamente.")
    return {"login": dados["sub"], "papel": dados["papel"], "nome": dados.get("nome", dados["sub"])}


def exigir(papel_minimo: str):
    async def verificar(usuario: dict = Depends(usuario_atual)) -> dict:
        if NIVEL[usuario["papel"]] < NIVEL[papel_minimo]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Ação permitida só para o papel {papel_minimo} ou superior.")
        return usuario
    return verificar


def criar_ticket(usuario: dict) -> str:
    agora = time.time()
    for t, (_, _, exp) in list(_tickets.items()):
        if exp < agora:
            del _tickets[t]
    ticket = secrets.token_urlsafe(24)
    _tickets[ticket] = (usuario["login"], usuario["papel"], agora + 30)
    return ticket


def consumir_ticket(ticket: str) -> str | None:
    """Ticket vale 30 s e só pode ser usado uma vez."""
    dados = _tickets.pop(ticket, None)
    if dados is None or dados[2] < time.time():
        return None
    return dados[0]
