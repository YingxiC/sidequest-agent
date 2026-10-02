"""`get_weather` — current conditions from Open-Meteo (free, no API key).

https://open-meteo.com/en/docs

Never raises: on bad input, network failure, timeout or a malformed
response it returns a WeatherReport with `ok=False` and `error` set, so the
caller can fall back to what the user said.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

API_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# WMO weather interpretation codes.
_RAIN_CODES = set(range(51, 68)) | {80, 81, 82}
_SNOW_CODES = set(range(71, 78)) | {85, 86}
_STORM_CODES = {95, 96, 99}
_FOG_CODES = {45, 48}

# Fetch a URL with a timeout and return the raw body. Injectable for tests.
HttpGet = Callable[[str, float], bytes]


@dataclass
class WeatherReport:
    ok: bool
    condition: str = "unknown"          # clear | cloudy | fog | rain | snow | storm | unknown
    temperature_c: float | None = None
    precipitation_mm: float | None = None
    # Max precipitation probability over the next few hours, in %.
    precipitation_probability: int | None = None
    # True when outdoor stops should be swapped for indoor ones.
    bad_for_outdoor: bool = False
    error: str | None = None
    source: str = "open-meteo"


def _default_http_get(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "sidequest-agent/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


@dataclass
class GeocodeResult:
    ok: bool
    name: str = ""
    lat: float | None = None
    lng: float | None = None
    error: str | None = None


def geocode(name: str, *, timeout: float = 5.0, http_get: HttpGet | None = None) -> GeocodeResult:
    """City name -> coordinates (Open-Meteo geocoding). Never raises."""
    if not name or not name.strip():
        return GeocodeResult(ok=False, error="empty location name")
    url = f"{GEOCODE_URL}?{urllib.parse.urlencode({'name': name.strip(), 'count': 1})}"
    try:
        data = json.loads((http_get or _default_http_get)(url, timeout))
    except urllib.error.HTTPError as exc:
        return GeocodeResult(ok=False, error=f"geocoding API returned HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return GeocodeResult(ok=False, error=f"geocoding API unreachable: {exc}")
    except ValueError as exc:
        return GeocodeResult(ok=False, error=f"unexpected geocoding response: {exc!r}")
    results = data.get("results") or []
    if not results:
        return GeocodeResult(ok=False, error=f"no place called '{name}' was found")
    top = results[0]
    label = ", ".join(p for p in (top.get("name"), top.get("admin1"), top.get("country")) if p)
    return GeocodeResult(ok=True, name=label, lat=top["latitude"], lng=top["longitude"])


def _condition(code: int) -> str:
    if code in _STORM_CODES:
        return "storm"
    if code in _SNOW_CODES:
        return "snow"
    if code in _RAIN_CODES:
        return "rain"
    if code in _FOG_CODES:
        return "fog"
    if code <= 1:
        return "clear"
    return "cloudy"


def get_weather(
    lat: float,
    lng: float,
    *,
    hours_ahead: int = 3,
    timeout: float = 5.0,
    http_get: HttpGet | None = None,
) -> WeatherReport:
    """Current weather at (lat, lng) plus rain chance over `hours_ahead` hours."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return WeatherReport(ok=False, error=f"invalid coordinates: {lat!r}, {lng!r}")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return WeatherReport(ok=False, error=f"coordinates out of range: {lat}, {lng}")

    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lng,
        "current": "temperature_2m,precipitation,weather_code",
        "hourly": "precipitation_probability",
        "forecast_hours": max(1, hours_ahead),
        "timezone": "auto",
    })
    url = f"{API_URL}?{params}"

    try:
        body = (http_get or _default_http_get)(url, timeout)
    except urllib.error.HTTPError as exc:
        return WeatherReport(ok=False, error=f"weather API returned HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return WeatherReport(ok=False, error=f"weather API unreachable: {exc}")

    try:
        data = json.loads(body)
        current = data["current"]
        code = int(current["weather_code"])
        temp = current.get("temperature_2m")
        precip = current.get("precipitation")
        probs = [p for p in data.get("hourly", {}).get("precipitation_probability", []) if p is not None]
    except (ValueError, KeyError, TypeError) as exc:
        return WeatherReport(ok=False, error=f"unexpected weather API response: {exc!r}")

    condition = _condition(code)
    max_prob = max(probs) if probs else None
    bad = (
        condition in {"rain", "snow", "storm"}
        or (precip is not None and precip >= 0.2)
        or (max_prob is not None and max_prob >= 60)
        or (temp is not None and (temp <= -5 or temp >= 35))
    )
    return WeatherReport(
        ok=True,
        condition=condition,
        temperature_c=temp,
        precipitation_mm=precip,
        precipitation_probability=max_prob,
        bad_for_outdoor=bad,
    )
