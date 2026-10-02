import json
import urllib.error

from integrations.weather import geocode, get_weather


def fake_http(payload):
    def _get(url, timeout):
        assert "latitude=40.73" in url
        return json.dumps(payload).encode()
    return _get


def test_rain_is_bad_for_outdoor():
    report = get_weather(40.73, -73.99, http_get=fake_http({
        "current": {"temperature_2m": 14.0, "precipitation": 1.2, "weather_code": 63},
        "hourly": {"precipitation_probability": [80, 70, 40]},
    }))
    assert report.ok and report.condition == "rain" and report.bad_for_outdoor
    assert report.precipitation_probability == 80


def test_clear_is_fine():
    report = get_weather(40.73, -73.99, http_get=fake_http({
        "current": {"temperature_2m": 21.0, "precipitation": 0.0, "weather_code": 0},
        "hourly": {"precipitation_probability": [0, 5, 10]},
    }))
    assert report.ok and report.condition == "clear" and not report.bad_for_outdoor


def test_network_error_does_not_raise():
    def down(url, timeout):
        raise urllib.error.URLError("no route to host")
    report = get_weather(40.73, -73.99, http_get=down)
    assert not report.ok and "unreachable" in report.error


def test_timeout_does_not_raise():
    def slow(url, timeout):
        raise TimeoutError("timed out")
    assert not get_weather(40.73, -73.99, http_get=slow).ok


def test_malformed_response():
    report = get_weather(40.73, -73.99, http_get=lambda u, t: b"<html>oops</html>")
    assert not report.ok and "unexpected" in report.error


def test_bad_coordinates():
    assert not get_weather(200, 0).ok
    assert not get_weather("abc", 0).ok


def test_geocode():
    body = {"results": [{"name": "New York", "admin1": "New York", "country": "United States",
                         "latitude": 40.71, "longitude": -74.0}]}
    res = geocode("New York", http_get=lambda u, t: json.dumps(body).encode())
    assert res.ok and res.lat == 40.71 and res.name == "New York, New York, United States"


def test_geocode_not_found_and_down():
    assert not geocode("zzz", http_get=lambda u, t: b"{}").ok

    def down(url, timeout):
        raise urllib.error.URLError("dns")
    assert "unreachable" in geocode("x", http_get=down).error
    assert not geocode("  ").ok
