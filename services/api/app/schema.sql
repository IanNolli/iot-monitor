-- PostgreSQL: cadastros, regras, alertas, jobs, modelos e auditoria.
-- As leituras dos sensores ficam no InfluxDB.

CREATE TABLE IF NOT EXISTS usuarios (
    id              SERIAL PRIMARY KEY,
    login           TEXT UNIQUE NOT NULL,
    nome            TEXT NOT NULL,
    papel           TEXT NOT NULL CHECK (papel IN ('visualizador', 'operador', 'administrador')),
    senha_hash      TEXT NOT NULL,
    falhas_login    INTEGER NOT NULL DEFAULT 0,
    bloqueado_ate   TIMESTAMPTZ,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dispositivos (
    id              TEXT PRIMARY KEY,
    nome            TEXT NOT NULL,
    classe          TEXT NOT NULL CHECK (classe IN ('sensor', 'atuador', 'equipamento')),
    zona            TEXT NOT NULL,
    grandeza        TEXT NOT NULL,
    unidade         TEXT NOT NULL DEFAULT '',
    faixa_min       DOUBLE PRECISION,
    faixa_max       DOUBLE PRECISION,
    controlavel     BOOLEAN NOT NULL DEFAULT false,
    ativo           BOOLEAN NOT NULL DEFAULT true,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS regras (
    id              SERIAL PRIMARY KEY,
    nome            TEXT NOT NULL,
    sensor_id       TEXT NOT NULL REFERENCES dispositivos(id) ON DELETE CASCADE,
    limite_liga     DOUBLE PRECISION NOT NULL,
    limite_desliga  DOUBLE PRECISION NOT NULL,
    atuador_id      TEXT NOT NULL REFERENCES dispositivos(id) ON DELETE CASCADE,
    ativa           BOOLEAN NOT NULL DEFAULT true,
    CHECK (limite_desliga < limite_liga)
);

CREATE TABLE IF NOT EXISTS configuracoes (
    chave           TEXT PRIMARY KEY,
    valor           JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS alertas (
    id              SERIAL PRIMARY KEY,
    dispositivo_id  TEXT NOT NULL,
    nivel           TEXT NOT NULL,
    mensagem        TEXT NOT NULL,
    saude           DOUBLE PRECISION,
    vida_util_h     DOUBLE PRECISION,
    aberto_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    fechado_em      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS jobs (
    id              UUID PRIMARY KEY,
    tipo            TEXT NOT NULL CHECK (tipo IN ('geracao', 'treino')),
    status          TEXT NOT NULL DEFAULT 'na_fila',
    progresso       INTEGER NOT NULL DEFAULT 0,
    mensagem        TEXT NOT NULL DEFAULT '',
    parametros      JSONB NOT NULL DEFAULT '{}',
    resultado       JSONB,
    criado_por      TEXT NOT NULL,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS modelos (
    versao          INTEGER PRIMARY KEY,
    metricas        JSONB NOT NULL,
    em_uso          BOOLEAN NOT NULL DEFAULT false,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auditoria (
    id              BIGSERIAL PRIMARY KEY,
    instante        TIMESTAMPTZ NOT NULL DEFAULT now(),
    usuario         TEXT,
    acao            TEXT NOT NULL,
    detalhe         JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_auditoria_instante ON auditoria (instante DESC);
CREATE INDEX IF NOT EXISTS idx_alertas_abertos ON alertas (dispositivo_id) WHERE fechado_em IS NULL;

-- Cadastro inicial dos dispositivos da casa (só se a tabela estiver vazia)
INSERT INTO dispositivos (id, nome, classe, zona, grandeza, unidade, faixa_min, faixa_max, controlavel)
SELECT * FROM (VALUES
    ('temp-sala', 'Temperatura da sala', 'sensor', 'sala', 'temperatura', '°C', 18.0, 28.0, false),
    ('lum-sala', 'Luminosidade da sala', 'sensor', 'sala', 'luminosidade', 'lux', 0.0, 1200.0, false),
    ('pres-sala', 'Presença na sala', 'sensor', 'sala', 'presenca', '', 0.0, 1.0, false),
    ('comp-geladeira', 'Compressor da geladeira', 'equipamento', 'cozinha', 'vibracao/corrente/temperatura', '', NULL, NULL, false),
    ('vent-sala', 'Ventilador da sala', 'atuador', 'sala', 'estado', '', NULL, NULL, false),
    ('lamp-sala', 'Lâmpada da sala', 'atuador', 'sala', 'estado', '', NULL, NULL, true)
) AS v(id, nome, classe, zona, grandeza, unidade, faixa_min, faixa_max, controlavel)
WHERE NOT EXISTS (SELECT 1 FROM dispositivos);

INSERT INTO regras (nome, sensor_id, limite_liga, limite_desliga, atuador_id)
SELECT 'Ventilador automático pela temperatura', 'temp-sala', 28.0, 26.0, 'vent-sala'
WHERE NOT EXISTS (SELECT 1 FROM regras);

INSERT INTO configuracoes (chave, valor) VALUES
    ('faixas_compressor', '{"vibracao": [0, 3.5], "corrente": [0, 1.6], "temperatura": [0, 55]}'),
    ('assistente_limite_por_minuto', '5')
ON CONFLICT (chave) DO NOTHING;
