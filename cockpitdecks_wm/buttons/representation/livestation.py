# ###########################
# Representation of a Metar in short textual summary form
#
import logging

from cockpitdecks.buttons.representation import WeatherStationPlot
from ...resources.weatheravwx import WeatherAVWX

logger = logging.getLogger(__name__)
# logger.setLevel(SPAM_LEVEL)
# logger.setLevel(logging.DEBUG)

FLIGHT_RULES = {"VFR": "green", "MVFR": "blue", "IFR": "red", "LIFR": "purple"}


class LiveStationPlot(WeatherStationPlot):
    """
    Depends on avwx-engine
    """

    REPRESENTATION_NAME = "live-station"

    def __init__(self, button: "Button"):
        WeatherStationPlot.__init__(self, button=button)
        icao = button._config.get(self.REPRESENTATION_NAME).get("station", self.DEFAULT_STATION)
        self.button = button
        self.weather_data = WeatherAVWX(icao=icao)
