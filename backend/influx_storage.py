"""Gravação e consulta de leituras no InfluxDB.

Nome escolhido para não conflitar com o pacote oficial `influxdb_client`.
"""

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

import config

MEASUREMENT = "temperatura"
FIELD = "valor"

_client = InfluxDBClient(url=config.INFLUX_URL, token=config.INFLUX_TOKEN, org=config.INFLUX_ORG)
_write_api = _client.write_api(write_options=SYNCHRONOUS)
_query_api = _client.query_api()

_FILTRO = (
    f'from(bucket: "{config.INFLUX_BUCKET}")\n'
    "  |> range(start: {inicio})\n"
    f'  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}" and r._field == "{FIELD}")\n'
)


def salvar(temperatura: float) -> None:
    """Grava uma leitura. Sem timestamp explícito: o InfluxDB usa o momento da gravação."""
    ponto = Point(MEASUREMENT).field(FIELD, float(temperatura))
    _write_api.write(bucket=config.INFLUX_BUCKET, record=ponto)


def _consultar(flux: str) -> list[dict]:
    tabelas = _query_api.query(flux)
    return [
        {"temperatura": round(registro.get_value(), 1), "timestamp": registro.get_time().isoformat()}
        for tabela in tabelas
        for registro in tabela.records
    ]


def consulta_ultima() -> str:
    return _FILTRO.format(inicio="-30d") + "  |> last()"


def consulta_historico(limite: int) -> str:
    # As mais recentes primeiro para aplicar o limite; depois em ordem cronológica para o gráfico
    return (
        _FILTRO.format(inicio="-1h")
        + '  |> sort(columns: ["_time"], desc: true)\n'
        + f"  |> limit(n: {limite})\n"
        + '  |> sort(columns: ["_time"])'
    )


def ultima() -> dict | None:
    leituras = _consultar(consulta_ultima())
    return leituras[0] if leituras else None


def historico(limite: int = 50) -> list[dict]:
    return _consultar(consulta_historico(limite))
