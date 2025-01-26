"""
A METAR is a weather situation at a named location, usually an airport.
"""

import logging
from typing import List, Any
from datetime import datetime, timezone
from functools import reduce
from textwrap import wrap

from avwx import Station, Metar, Taf
import pytaf

from cockpitdecks.resources.weather import WeatherData

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


def nowutc() -> datetime:
    return datetime.now(timezone.utc)


class WeatherAVWX(WeatherData):

    def __init__(self, icao: str, taf: bool = False):
        WeatherData.__init__(self, name=icao, config={})
        self._created = datetime.now()
        self._updated: datetime

        self.previous_weather = []

        self.icao = icao
        self.taf = taf
        self._forecast = []

        self.imperial = False  # currently unused, reminder to think about it (METAR differ in US/rest of the world)
        # can be guessed from METAR pressure indicator: Q1013 or A2992.

        self.update_time = 10 * 60  # secs

        # working variables
        self._raw: str

        # Debugging values
        # self._check_freq = 10  # seconds
        # self._station_check_freq = 60  # seconds
        # self._weather_check_freq = 30  # seconds

        self.init()

    def init(self):
        self.station = Station.from_icao(self.icao)
        if self.station is not None:
            if self.update_weather():
                self.weather_changed()
        else:
            logger.warning(f"invalid or non-existant weather station {self.icao}")

    # ################################################
    # WeatherData Interface
    #
    @property
    def label(self):
        return self.station.icao if self.station is not None else "Weather"

    def set_station(self, station: Any):
        if type(station) is Station:
            logger.debug(f"new station {station.icao} ({type(station)})")
            self.station = station
            return
        newstation = Station.from_icao(ident=station)
        if newstation is not None:
            logger.debug(f"new station {newstation.icao} ({type(newstation)})")
            self.station = newstation
            return
        logger.warning(f"could not change to station {station} ({type(station)})")

    def check_station(self) -> bool:
        """Returns True if station is not defined or is different from weather stattion."""
        if not hasattr(self, "_station") or self._station is None:
            logger.warning("no station, this should never happen")
            return True
        if self.station.icao != self.weather.station.icao:
            logger.debug(f"station changed to {self.station.icao}")
            return True
        logger.debug("station unchanged")
        return False

    def station_changed(self):
        """Executed when station has changed."""
        logger.debug("station changed, updating weather")
        if self.update_weather():
            self.weather_changed()

    def weather_changed(self):
        """Called when weather data has changed"""
        if self.update_weather():
            logger.debug("weather updated")
            super().weather_changed()
        else:
            logger.debug("weather unchanged")

    # ################################################
    # Utility functions
    #
    def update_weather(self) -> bool:
        # 1. Weather data update if weather data is available and station has not changed
        if hasattr(self, "_weather") and self._weather is not None:
            if self._weather.station == self.station:  # just need to update metar
                logger.debug("station not changed")
                if self._weather.update():
                    logger.info(f"weather checked, changed: {self._weather.raw}")
                    self._weather_last_checked = nowutc()
                    return True
                logger.info("weather checked, unchanged")
                return False
            else:
                logger.debug("station changed, creating new weather")
        # 2. New weather data if no weather data or station has changed.
        logger.debug("new weather..")
        if self.taf:
            self._weather = Taf(self.station.icao)
            self._forecast = []
        else:
            self._weather = Metar(self.station.icao)
        updated = self._weather.update()
        logger.debug(f"weather created: {updated}")
        if updated:
            self._weather_last_checked = nowutc()
            logger.info(f"weather updated: {self._weather.raw}")
        return updated

    def check_weather(self) -> bool:
        """Check whether weather needs updating.

        Weather needs updating if:
        - The is no weather data
        - Station has changed
        - Weather data is outdated
        """
        if not hasattr(self, "_weather") or self._weather is None or self._weather_last_checked is None:
            logger.debug("no weather")
            return True
        now = nowutc()
        if (now - self._weather_last_checked).seconds > self._weather_check_freq:
            logger.debug("weather expired")
            return True
        else:
            logger.debug("weather not expired")
        return False

    def has_weather(self):
        # No "raw" attribue, means weather defined but not updated yet
        return self.weather is not None and getattr(self.weather, "raw", None) is not None

    def metar(self) -> str | None:
        return self._weather.raw if hasattr(self.weather, "raw") and not self.taf else None

    def get_forecast_page(self, page: int = 0, width: int = 21) -> List[str]:
        if not self.taf:
            return []
        if len(self._forecast) == 0:
            taf_text = pytaf.Decoder(pytaf.TAF(self.weather.raw)).decode_taf()
            # Split TAF in blocks of forecasts
            # print(taf_text)
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
    w = WeatherAVWX(icao="OTHH", taf=True)
    print(w.weather.raw)
    if type(w.weather) is Taf:
        print("\n".join(w.weather.summary))
        print("---")
        print("\n".join(w.get_forecast_page(0)))
    else:
        print("\n".join(w.weather.summary.split(", ")))
    # w.update_weather()
