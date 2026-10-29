"""Consultas ao histórico no InfluxDB."""

import re

from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

from . import config

_cliente: InfluxDBClientAsync | None = None
SEGURO = re.compile(r"^[a-z0-9_-]+$")


def cliente() -> InfluxDBClientAsync:
    global _cliente
    if _cliente is None:
        _cliente = InfluxDBClientAsync(url=config.INFLUX_URL, token=config.INFLUX_TOKEN, org=config.INFLUX_ORG)
    return _cliente


async def serie(measurement: str, dispositivo: str, campos: list[str], minutos: int, bucket: str = config.INFLUX_BUCKET,
                tag: str = "dispositivo", pontos: int = 120) -> dict[str, list]:
    """Série agregada (média por janela) com ~`pontos` pontos no período."""
    for valor in [measurement, dispositivo, bucket, tag, *campos]:
        if not SEGURO.match(valor):
            raise ValueError("parâmetro inválido")
    minutos = max(1, min(minutos, 60 * 24 * 400))  # até 400 dias (amostra do laboratório)
    janela = max(5, minutos * 60 // pontos)
    filtro_campos = " or ".join(f'r._field == "{c}"' for c in campos)
    flux = f'''
from(bucket: "{bucket}")
  |> range(start: -{minutos}m)
  |> filter(fn: (r) => r._measurement == "{measurement}" and r.{tag} == "{dispositivo}")
  |> filter(fn: (r) => {filtro_campos})
  |> aggregateWindow(every: {janela}s, fn: mean, createEmpty: false)
'''
    tabelas = await cliente().query_api().query(flux)
    resultado: dict[str, list] = {c: [] for c in campos}
    for tabela in tabelas:
        for r in tabela.records:
            resultado[r.get_field()].append([r.get_time().isoformat(), round(r.get_value(), 3)])
    return resultado


async def contar_pontos(bucket: str) -> int:
    flux = f'from(bucket: "{bucket}") |> range(start: -400d) |> count() |> group() |> sum()'
    try:
        tabelas = await cliente().query_api().query(flux)
        return int(sum(r.get_value() for t in tabelas for r in t.records))
    except Exception:
        return 0


async def valores_tag(bucket: str, tag: str) -> list[str]:
    if not (SEGURO.match(bucket) and SEGURO.match(tag)):
        raise ValueError("parâmetro inválido")
    flux = f'import "influxdata/influxdb/schema"\nschema.tagValues(bucket: "{bucket}", tag: "{tag}", start: -400d)'
    tabelas = await cliente().query_api().query(flux)
    return sorted(str(r.get_value()) for t in tabelas for r in t.records)
