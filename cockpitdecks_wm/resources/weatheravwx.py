"""
A METAR is a weather situation at a named location, usually an airport.
"""

import logging
from typing import List
from datetime import datetime, timezone
from functools import reduce
from textwrap import wrap

from avwx import Station, Metar, Taf
import pytaf

from cockpitdecks.resources.weather import WeatherData

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class WeatherAVWX(WeatherData):

    def __init__(self, icao: str, taf: bool = False):
        WeatherData.__init__(self, name=icao, config={})
        self._created = datetime.now()
        self._updated: datetime

        self.previous_weather = []

        self.icao = icao
        self.taf = taf
        self._forecast = []

        self.auto = False
        self.imperial = False  # currently unused, reminder to think about it (METAR differ in US/rest of the world)

        self.update_time = 10 * 60  # secs

        # working variables
        self._raw: str

        self.init()

    def init(self):
        self.station = Station.from_icao(self.icao)
        if self.station is not None:
            self.update_weather()
        else:
            logger.warning(f"invalid or non-existant weather station {self.icao}")

    def check_station(self) -> bool:
        """Returns True if station is not defined or is different from weather stattion."""
        if not hasattr(self, "_station") or self._station is None:
            return True
        return self.station.icao != self.weather.station.icao

    def station_changed(self):
        """Executed when station has changed."""
        self.update_weather()

    def check_weather(self) -> bool:
        """Check whether weather needs updating.

        Weather needs updating if:
        - The is no weather data
        - Station has changed
        - Weather data is outdated
        """
        # 1. No weather data (new)
        if not hasattr(self, "_weather") or self._weather is None:
            return True
        # 2. Station non existant or changed.
        if self.check_station():
            return True
        # 3. Weather data is outdated
        diff = datetime.now(timezone.utc) - self.weather.last_updated
        return diff.seconds > self.update_time

    def has_weather(self):
        # No "raw" attribue, means weather defined but not updated yet
        return self.weather is not None and getattr(self.weather, "raw", None) is not None

    def metar(self) -> str | None:
        return self._weather.raw if hasattr(self.weather, "raw") and not self.taf else None

    def update_weather(self) -> bool:
        if self.check_weather():
            # 1. Weather data update if weather data is available and station has not changed
            if hasattr(self, "_weather") and self._weather is not None:
                if self._weather.station == self.station:  # just need to update metar
                    if self._weather.update():
                        self.weather_changed()
                    return True
            # 2. New weather data if no weather data or station has changed.
            if self.taf:
                self._weather = Taf(self.station.icao)
                self._forecast = []
            else:
                self._weather = Metar(self.station.icao)
            updated = self._weather.update()
            self.weather_changed()
            return True  # updated
        else:
            logger.debug("weather does not need updating")
        return False

    def get_forecast_page(self, page: int = 0, width: int = 21) -> List[str]:
        if not self.taf:
            return []
        if len(self._forecast) == 0:
            taf_text = pytaf.Decoder(pytaf.TAF(self.weather.raw)).decode_taf()
            # Split TAF in blocks of forecasts
            forecast = []
            prevision = []
            for line in taf_text.split("\n"):
                if len(line.strip()) > 0:
                    prevision.append(line)
                else:
                    forecast.append(prevision)
                    prevision = []
            while len(forecast[-1]) == 0:
                forecast = forecast[:-1]
            self._forecast = forecast
        l = len(self._forecast)
        a = page % l
        # s = "●" if len(forecast) < 2 else "o"*a+"●"+"o"*(len(forecast)-a-1)  # ●○
        text = [f"Forecast page {1 + a} / {l}"] + self._forecast[a]
        return reduce(lambda x, t: x + wrap(t, width=width), text, [])

    # Past data
    def get_metar_for(self, icao: str) -> list:
        return filter(lambda m: m.startswith(icao), self.previous_weather)

    def get_older_metar(self, icao: str) -> list:
        candidates = self.get_metar_for(icao=icao)
        return candidates

    # Future
    def get_taf_for(self, icao: str) -> list:
        return filter(lambda m: m.startswith(icao), self.previous_weather)

    def has_trend(self) -> bool:
        return len(self.previous_weather) > 0


# For testing:
# $ python cockpitdecks_wm/buttons/representation/ogimet.py
if __name__ == "__main__":
    w = WeatherAVWX(icao="EDDM", taf=False)
    print(w.weather.raw)
    if type(w.weather) is Taf:
        print("\n".join(w.weather.summary))
    else:
        print("\n".join(w.weather.summary.split(", ")))
    # w.update_weather()
