import requests
from flask import jsonify, current_app

from app.api import api_bp
from app.auth.decorators import aprovado_required
from app.extensions import cache
from app.models import Cidade

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Mapeamento simplificado dos códigos WMO usados pelo Open-Meteo
# (https://open-meteo.com/en/docs) para descrição em PT-BR + ícone Font Awesome.
_WMO_CODES = {
    0: ("Céu limpo", "fa-sun"),
    1: ("Poucas nuvens", "fa-cloud-sun"),
    2: ("Parcialmente nublado", "fa-cloud-sun"),
    3: ("Nublado", "fa-cloud"),
    45: ("Neblina", "fa-smog"),
    48: ("Neblina densa", "fa-smog"),
    51: ("Garoa fraca", "fa-cloud-rain"),
    53: ("Garoa", "fa-cloud-rain"),
    55: ("Garoa forte", "fa-cloud-rain"),
    61: ("Chuva fraca", "fa-cloud-rain"),
    63: ("Chuva", "fa-cloud-showers-heavy"),
    65: ("Chuva forte", "fa-cloud-showers-heavy"),
    71: ("Neve fraca", "fa-snowflake"),
    73: ("Neve", "fa-snowflake"),
    75: ("Neve forte", "fa-snowflake"),
    80: ("Pancadas de chuva", "fa-cloud-showers-heavy"),
    81: ("Pancadas de chuva", "fa-cloud-showers-heavy"),
    82: ("Pancadas fortes", "fa-cloud-showers-heavy"),
    95: ("Trovoadas", "fa-bolt"),
    96: ("Trovoadas com granizo", "fa-cloud-bolt"),
    99: ("Trovoadas com granizo", "fa-cloud-bolt"),
}


@cache.memoize(timeout=6 * 3600)
def _geocodificar(nome_cidade: str):
    """Converte nome da cidade em latitude/longitude. Cacheado por várias
    horas, já que a localização de uma cidade não muda."""
    resp = requests.get(
        GEOCODE_URL,
        params={"name": nome_cidade, "count": 1, "language": "pt", "format": "json"},
        timeout=5,
    )
    resp.raise_for_status()
    resultados = resp.json().get("results") or []
    if not resultados:
        return None
    r = resultados[0]
    return {"lat": r["latitude"], "lon": r["longitude"]}


@cache.memoize(timeout=1800)
def _clima_atual(lat: float, lon: float):
    """Busca o clima atual. Cacheado por 30 minutos por coordenada."""
    resp = requests.get(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "current_weather": True,
            "timezone": "America/Sao_Paulo",
        },
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json().get("current_weather")


@api_bp.get("/cidades/<int:cidade_id>/clima")
@aprovado_required
def clima_cidade(cidade_id):
    cidade = Cidade.query.get_or_404(cidade_id)
    try:
        coords = _geocodificar(f"{cidade.nome}, Mato Grosso do Sul, Brasil")
        if not coords:
            coords = _geocodificar(cidade.nome)
        if not coords:
            return jsonify({"disponivel": False})

        atual = _clima_atual(coords["lat"], coords["lon"])
        if not atual:
            return jsonify({"disponivel": False})

        codigo = atual.get("weathercode")
        descricao, icone = _WMO_CODES.get(codigo, ("Indisponível", "fa-cloud"))
        return jsonify({
            "disponivel": True,
            "temperatura": atual.get("temperature"),
            "ventoKmh": atual.get("windspeed"),
            "descricao": descricao,
            "icone": icone,
        })
    except requests.RequestException as exc:
        current_app.logger.warning("Falha ao buscar clima para %s: %s", cidade.nome, exc)
        return jsonify({"disponivel": False})
