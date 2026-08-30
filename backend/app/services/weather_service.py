"""G2-S5 — Weather provider abstraction for the Home Dashboard.

DashboardService consumes the ``WeatherProvider`` interface only; the
OpenWeather-specific payload shape never leaks past this module. When the
integration is disabled, misconfigured, or the provider fails, the dashboard
degrades gracefully to ``weather = None`` — weather is never fabricated.
"""
from typing import Optional

import httpx
from pydantic import BaseModel

from backend.app.core.config import settings
from backend.app.core.logging import logger


class WeatherOut(BaseModel):
    """Normalized, provider-agnostic weather DTO used by the dashboard."""

    temperature_c: float
    condition: str
    summary: str
    provider: str


class WeatherProvider:
    """Interface every weather provider implements."""

    def get_current_weather(self, latitude: float, longitude: float) -> Optional[WeatherOut]:
        raise NotImplementedError


class NullWeatherProvider(WeatherProvider):
    """Safe default used when the integration is disabled or unconfigured."""

    def get_current_weather(self, latitude: float, longitude: float) -> Optional[WeatherOut]:
        return None


class OpenWeatherProvider(WeatherProvider):
    """Real OpenWeather current-conditions client.

    Reads its key/base URL exclusively from application settings — the key is
    never hardcoded, logged, or returned to clients. All network/parse
    failures degrade to ``None`` so the dashboard keeps working.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openweathermap.org",
        timeout_seconds: float = 10.0,
        units: str = "metric",
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._units = units

    def get_current_weather(self, latitude: float, longitude: float) -> Optional[WeatherOut]:
        # Malformed coordinates never reach the network.
        if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
            logger.warn("weather request rejected: invalid coordinates", lat=latitude, lon=longitude)
            return None
        try:
            resp = httpx.get(
                f"{self._base_url}/data/2.5/weather",
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "appid": self._api_key,
                    "units": self._units,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            logger.warn("weather provider timeout", base_url=self._base_url)
            return None
        except httpx.HTTPError as exc:
            logger.warn("weather provider http failure", error=str(exc))
            return None
        except ValueError:
            logger.warn("weather provider returned malformed JSON")
            return None

        try:
            weather_list = data.get("weather") or []
            main = data.get("main") or {}
            temp = main.get("temp")
            if temp is None or not weather_list:
                logger.warn("weather provider response missing expected fields")
                return None
            condition = str(weather_list[0].get("main") or "Unknown")
            description = str(weather_list[0].get("description") or condition)
            return WeatherOut(
                temperature_c=float(temp),
                condition=condition,
                summary=description,
                provider="openweather",
            )
        except (AttributeError, TypeError, IndexError) as exc:
            logger.warn("weather provider response parse failure", error=str(exc))
            return None


def get_weather_provider() -> WeatherProvider:
    """Resolve the configured provider; anything unconfigured -> Null provider."""
    if settings.OPENWEATHER_ENABLED and settings.OPENWEATHER_API_KEY:
        return OpenWeatherProvider(
            api_key=settings.OPENWEATHER_API_KEY,
            base_url=settings.OPENWEATHER_BASE_URL,
            timeout_seconds=settings.OPENWEATHER_TIMEOUT_SECONDS,
            units=settings.OPENWEATHER_UNITS,
        )
    return NullWeatherProvider()
