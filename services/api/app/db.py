"""Pool de conexões com o PostgreSQL, criação do schema e auditoria."""

import json
from pathlib import Path

import asyncpg
import bcrypt

from . import config

pool: asyncpg.Pool | None = None


async def _configurar_conexao(conexao: asyncpg.Connection) -> None:
    await conexao.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def iniciar() -> None:
    global pool
    pool = await asyncpg.create_pool(config.POSTGRES_DSN, min_size=2, max_size=10, init=_configurar_conexao)
    async with pool.acquire() as c:
        await c.execute(Path(__file__).with_name("schema.sql").read_text())
        # Usuários de demonstração: senhas vêm do .env (o hash é atualizado se o .env mudar)
        for login, (nome, papel, senha) in config.USUARIOS_DEMO.items():
            atual = await c.fetchval("SELECT senha_hash FROM usuarios WHERE login = $1", login)
            if atual is None or not bcrypt.checkpw(senha.encode(), atual.encode()):
                hash_ = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
                await c.execute(
                    """INSERT INTO usuarios (login, nome, papel, senha_hash) VALUES ($1, $2, $3, $4)
                       ON CONFLICT (login) DO UPDATE SET senha_hash = EXCLUDED.senha_hash, papel = EXCLUDED.papel""",
                    login, nome, papel, hash_)


async def encerrar() -> None:
    if pool:
        await pool.close()


async def auditar(usuario: str | None, acao: str, detalhe: dict | None = None) -> None:
    await pool.execute("INSERT INTO auditoria (usuario, acao, detalhe) VALUES ($1, $2, $3)", usuario, acao, detalhe or {})
