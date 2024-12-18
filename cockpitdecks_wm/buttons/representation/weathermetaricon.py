# ###########################
# Buttons were isolated here because they use specific packages (avwx-engine)
# and rely on external services.
#
# The information these icon communicates DOES NOT come from X-Plane
# but from external, real services.
#
# METAR are usually updated every 30 min at specified times.
# Algorithm could be updated to take that into account: Update at hours+10 or hours+40
# if not updated in the last 30 minutes. (Could be cached in file?)
import logging
import random
import re
import math
from functools import reduce
from datetime import datetime, timezone, tzinfo

from avwx import Station, Metar, Taf
from suntime import Sun
from zoneinfo import ZoneInfo
from timezonefinder import TimezoneFinder

# these packages have better summary/description of decoded METAR/TAF
from metar import Metar as MetarDesc
import pytaf

from PIL import Image, ImageDraw

from cockpitdecks import ICON_SIZE
from cockpitdecks.resources.iconfonts import (
    WEATHER_ICONS,
    WEATHER_ICON_FONT,
    DEFAULT_WEATHER_ICON,
)
from cockpitdecks.resources.color import light_off, TRANSPARENT_PNG_COLOR
from cockpitdecks.simulator import SimulatorData, SimulatorDataListener

from cockpitdecks.buttons.representation.draw_animation import DrawAnimation


logger = logging.getLogger(__name__)
# logger.setLevel(SPAM_LEVEL)
# logger.setLevel(logging.DEBUG)

# #############
# Local constant
#
KW_NAME = "iconName"  # "cloud",
KW_DAY = "day"  # 2,  0=night, 1=day, 2=day or night
KW_NIGHT = "night"  # 1,
KW_TAGS = "descriptor"  # [],
KW_PRECIP = "precip"  # "RA",
KW_VIS = "visibility"  # [""],
KW_CLOUD = "cloud"  # ["BKN"],
KW_WIND = "wind"  # [0, 21]

WI_PREFIX = "wi_"
DAY = "day_"
NIGHT = "night_"
NIGHT_ALT = "night_alt_"

KW_CAVOK = "clear"  # Special keyword for CAVOK day or night
CAVOK_DAY = "wi_day_sunny"
CAVOK_NIGHT = "wi_night_clear"


class WI:
    """
    Simplified weather icon
    """

    I_S = [
        "_sunny",
        "_cloudy",
        "_cloudy_gusts",
        "_cloudy_windy",
        "_fog",
        "_hail",
        "_haze",
        "_lightning",
        "_rain",
        "_rain_mix",
        "_rain_wind",
        "_showers",
        "_sleet",
        "_sleet_storm",
        "_snow",
        "_snow_thunderstorm",
        "_snow_wind",
        "_sprinkle",
        "_storm_showers",
        "_sunny_overcast",
        "_thunderstorm",
        "_windy",
        "_cloudy_high",
        "_light_wind",
    ]

    DB = [
        {
            KW_NAME: KW_CAVOK,
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: ["CAVOK", "NCD"],
            KW_CLOUD: [""],
            KW_WIND: [0, 21],
        },
        {
            KW_NAME: "cloud",
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: [""],
            KW_CLOUD: ["BKN"],
            KW_WIND: [0, 21],
        },
        {
            KW_NAME: "cloudy",
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: [""],
            KW_CLOUD: ["OVC"],
            KW_WIND: [0, 21],
        },
        {
            KW_NAME: "cloudy-gusts",
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: [""],
            KW_CLOUD: ["SCT", "BKN", "OVC"],
            KW_WIND: [22, 63],
        },
        {
            KW_NAME: "rain",
            KW_TAGS: [],
            KW_PRECIP: "RA",
            KW_VIS: [""],
            KW_CLOUD: [""],
            KW_WIND: [0, 21],
        },
        {
            KW_NAME: "rain-wind",
            KW_TAGS: [],
            KW_PRECIP: "RA",
            KW_VIS: [""],
            KW_CLOUD: [""],
            KW_WIND: [22, 63],
        },
        {
            KW_NAME: "showers",
            KW_TAGS: ["SH"],
            KW_PRECIP: "",
            KW_VIS: [""],
            KW_CLOUD: [""],
            KW_WIND: [0, 63],
        },
        {
            KW_NAME: "fog",
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: ["BR", "FG"],
            KW_CLOUD: [""],
            KW_WIND: [0, 63],
        },
        {
            KW_NAME: "storm-showers",
            KW_TAGS: ["TS", "SH"],
            KW_PRECIP: "",
            KW_VIS: [""],
            KW_CLOUD: [""],
            KW_WIND: [0, 63],
        },
        {
            KW_NAME: "thunderstorm",
            KW_TAGS: ["TS"],
            KW_PRECIP: "",
            KW_VIS: [""],
            KW_CLOUD: [""],
            KW_WIND: [0, 63],
        },
        {
            KW_NAME: "windy",
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: ["CAVOK", "NCD"],
            KW_CLOUD: [""],
            KW_WIND: [22, 33],
        },
        {
            KW_NAME: "strong-wind",
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: ["CAVOK", "NCD"],
            KW_CLOUD: [""],
            KW_WIND: [34, 63],
        },
        {
            KW_NAME: "cloudy",
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: [""],
            KW_CLOUD: ["FEW", "SCT"],
            KW_WIND: [0, 21],
        },
        {
            KW_NAME: "cloudy",
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: [""],
            KW_CLOUD: ["FEW", "SCT"],
            KW_WIND: [0, 21],
        },
        {
            KW_NAME: "cloudy-gusts",
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: [""],
            KW_CLOUD: ["SCT", "BKN", "OVC"],
            KW_WIND: [22, 63],
        },
        {
            KW_NAME: "cloudy-gusts",
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: [""],
            KW_CLOUD: ["SCT", "BKN", "OVC"],
            KW_WIND: [22, 63],
        },
        {
            KW_NAME: "cloudy-windy",
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: [""],
            KW_CLOUD: ["FEW", "SCT"],
            KW_WIND: [22, 63],
        },
        {
            KW_NAME: "cloudy-windy",
            KW_TAGS: [],
            KW_PRECIP: "",
            KW_VIS: [""],
            KW_CLOUD: ["FEW", "SCT"],
            KW_WIND: [22, 63],
        },
        {
            KW_NAME: "snow",
            KW_TAGS: [],
            KW_PRECIP: "SN",
            KW_VIS: [""],
            KW_CLOUD: [""],
            KW_WIND: [0, 21],
        },
        {
            KW_NAME: "snow-wind",
            KW_TAGS: [],
            KW_PRECIP: "SN",
            KW_VIS: [""],
            KW_CLOUD: [""],
            KW_WIND: [22, 63],
        },
    ]

    def __init__(self, day: bool, cover=float, wind=float, precip=float, special=float):
        self.day = day  # night=False, time at location (local time)
        self.cover = cover  # 0=clear, 1=overcast
        self.wind = wind  # 0=no wind, 1=storm
        self.precip = precip  # 0=none, 1=rain1, 2=rain2, 3=snow, 4=hail
        self.special = special  # 0=none, 1=fog, 2=sandstorm


def distance(origin, destination):
    """
    Calculate the Haversine distance.

    Parameters
    ----------
    origin : tuple of float
        (lat, long)
    destination : tuple of float
        (lat, long)

    Returns
    -------
    distance_in_km : float

    Examples
    --------
    >>> origin = (48.1372, 11.5756)  # Munich
    >>> destination = (52.5186, 13.4083)  # Berlin
    >>> round(distance(origin, destination), 1)
    504.2
    """
    lat1, lon1 = origin
    lat2, lon2 = destination
    radius = 6371  # km

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) * math.sin(dlat / 2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) * math.sin(dlon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    d = radius * c

    return d


class WeatherMetarIcon(DrawAnimation, SimulatorDataListener):
    """
    Depends on avwx-engine
    """

    REPRESENTATION_NAME = "weather-metar"

    MIN_UPDATE = 60.0  # seconds between two station updates
    CHECK_STATION = 60.0  # seconds, anim runs every so often to check for movements
    MIN_DISTANCE_MOVE_KM = 0.0  # km
    DEFAULT_STATION = "EBBR"  # LFBO for Airbus?

    PARAMETERS = {
        "speed": {"type": "integer", "prompt": "Refresh weather (seconds)"},
        "Refresh location": {"type": "integer", "prompt": "Refresh location (seconds)"},
    }

    def __init__(self, button: "Button"):
        self._moved = False  # True if we get Metar for location at (lat, lon), False if Metar for default station

        self.use_simulation = False  # If False, use current weather METAR/TAF, else use simulator METAR and date/time; no TAF.
        # This should be decide by a dataref in XPlane, use real weather, use real date/time.

        self.weather = button._config.get(self.REPRESENTATION_NAME)
        if self.weather is not None and isinstance(self.weather, dict):
            button._config["animation"] = button._config.get(self.REPRESENTATION_NAME)
        else:
            button._config["animation"] = {}
            self.weather = {}

        self._last_updated: datetime | None = None
        self._cache = None
        self._busy_updating = False  # need this for race condition during update (anim loop)

        refresh_location = self.weather.get("refresh-location", self.CHECK_STATION)  # minutes
        WeatherMetarIcon.MIN_UPDATE = int(refresh_location) * 60

        # Working variables
        self.station: Station | None = None
        self.sun: Sun | None = None

        self.metar: Metar | None = None
        self.taf: Taf | None = None
        self.show = self.weather.get("summary")

        self.weather_icon: str | None = None
        self.update_position = False

        self.icao_dataref_path = button._config.get("string-dataref")
        self.icao_dataref = None

        DrawAnimation.__init__(self, button=button)
        SimulatorDataListener.__init__(self)

        # "Animation" (refresh)
        speed = self.weather.get("refresh", 30)  # minutes, should be ~30 minutes
        self.speed = int(speed) * 60  # minutes

        self.icon_color = self.weather.get("icon-color", self.get_attribute("text-color"))
        self._no_coord_warn = 0

    def init(self):
        if self._inited:
            return

        # Initialize datarefs to communicate weather main parameters
        self.weather_pressure = self.button.sim.get_internal_data("weather:pressure")
        self.weather_wind_speed = self.button.sim.get_internal_data("weather:wind_speed")
        self.weather_temperature = self.button.sim.get_internal_data("weather:temperature")
        self.weather_dew_point = self.button.sim.get_internal_data("weather:dew_point")

        if self.icao_dataref_path is not None:
            # toliss_airbus/flightplan/departure_icao
            # toliss_airbus/flightplan/destination_icao
            self.icao_dataref = self.button.sim.get_data(self.icao_dataref_path, is_string=True)
            self.icao_dataref.add_listener(self)  # the representation gets notified directly.
            self.simulator_data_changed(self.icao_dataref)
            self._inited = True
            logger.debug(f"initialized, waiting for dataref {self.icao_dataref.name}")
            return

        icao = self.weather.get("station")
        if icao is None:
            icao = WeatherMetarIcon.DEFAULT_STATION  # start with default position
            logger.debug(f"default station installed {icao}")
            self.update_position = True  # will be updated
        self.station = Station.from_icao(icao)
        if self.station is not None:
            self.sun = Sun(self.station.latitude, self.station.longitude)
            self.button._config["label"] = icao
            if self.metar is not None and self.metar.data is not None:
                logger.debug(f"data for {self.station.icao}")
                self.weather_pressure.update_value(self.metar.data.altimeter.value)
                logger.debug(f"pressure {self.metar.data.altimeter.value}")
                self.weather_wind_speed.update_value(self.metar.data.wind_speed.value)
                logger.debug(f"wind speed {self.metar.data.wind_speed.value}")
                self.weather_temperature.update_value(self.metar.data.temperature.value)
                logger.debug(f"temperature {self.metar.data.temperature.value}")
                self.weather_dew_point.update_value(self.metar.data.dewpoint.value)
                logger.debug(f"dew point {self.metar.data.dewpoint.value}")
            else:
                logger.debug(f"no metar for {self.station.icao}")
            self.weather_icon = self.select_weather_icon()
            logger.debug(f"Metar updated for {self.station.icao}, icon={self.weather_icon}, updated={self._last_updated}")
        self._inited = True

    def at_default_station(self):
        ret = True
        if self.weather is not None and self.station is not None:
            ret = not self._moved and self.station.icao == self.weather.get("station", WeatherMetarIcon.DEFAULT_STATION)
            logger.debug(
                f"currently at {self.station.icao}, default station {self.weather.get('station', WeatherMetarIcon.DEFAULT_STATION)}, moved={self._moved}, returns {ret}"
            )
        return ret

    def get_simulator_data(self) -> set:
        ret = {
            "sim/flightmodel/position/latitude",
            "sim/flightmodel/position/longitude",
            "sim/cockpit2/clock_timer/local_time_hours",
            self.weather_pressure.name,
            self.weather_wind_speed.name,
            self.weather_temperature.name,
            self.weather_dew_point.name,
        }
        if self.icao_dataref_path is not None:
            ret.add(self.icao_dataref_path)
        return ret

    def should_run(self) -> bool:
        """
        Check conditions to animate the icon.
        In this case, always runs
        """
        return self._inited and self.button.on_current_page()

    def simulator_data_changed(self, data: SimulatorData):
        # what if Dataref.internal_dataref_path("weather:*") change?
        if data.name != self.icao_dataref_path:
            return
        icao = data.value()
        if icao is None or icao == "":  # no new station, stick or current
            return
        if self.station is not None and icao == self.station.icao:  # same station
            return
        self.station = Station.from_icao(icao)
        if self.station is not None:
            self.sun = Sun(self.station.latitude, self.station.longitude)
        self.button._config["label"] = icao

        # invalidate previous values
        self.metar = None
        self._cache = None
        self.update(force=True)

    def get_station(self):
        if not self.update_position:
            return None

        if self._last_updated is not None and not self.at_default_station():
            now = datetime.now()
            diff = now.timestamp() - self._last_updated.timestamp()
            if diff < WeatherMetarIcon.MIN_UPDATE:
                logger.debug(f"updated less than {WeatherMetarIcon.MIN_UPDATE} secs. ago ({diff}), skipping update.. ({self.speed})")
                return None
            logger.debug(f"updated {diff} secs. ago")

        # If we are at the default station, we check where we are to see if we moved.
        lat = self.button.get_simulator_data_value("sim/flightmodel/position/latitude")
        lon = self.button.get_simulator_data_value("sim/flightmodel/position/longitude")

        if lat is None or lon is None:
            if (self._no_coord_warn % 10) == 0:
                logger.warning("no coordinates")
                self._no_coord_warn = self._no_coord_warn + 1
            if self.station is None:  # If no station, attempt to suggest the default one if we find it
                icao = self.weather.get("station", WeatherMetarIcon.DEFAULT_STATION)
                logger.warning(f"no station, getting default {icao}")
                return Station.from_icao(icao)
            return None

        logger.debug(f"closest station to lat={lat},lon={lon}")
        (nearest, coords) = Station.nearest(lat=lat, lon=lon, max_coord_distance=150000)
        logger.debug(f"nearest={nearest}")
        ## compute distance and require minimum displacment
        dist = 0.0
        if self.station is not None:
            dist = distance((self.station.latitude, self.station.longitude), (lat, lon))
            logger.info(f"moved={round(dist,3)}")
            if dist > self.MIN_DISTANCE_MOVE_KM:
                self._moved = True
        else:
            logger.debug("no station")
        return nearest

    def update_metar(self, create: bool = False):
        if create:
            self.metar = Metar(self.station.icao)
        if not self.needs_update():
            return False
        before = self.metar.raw
        updated = self.metar.update()
        self._last_updated = datetime.now()
        if updated:
            logger.info(f"station {self.station.icao}, Metar updated")
            logger.info(f"update: {before} -> {self.metar.raw}")
            if self.show is not None:
                self.print()
        else:
            logger.info(f"station {self.station.icao}, Metar fetched, unchanged")
        return updated

    def print(self):
        # Print current situation
        if self.has_metar("raw") and self.show == "nice":
            obs = MetarDesc.Metar(self.metar.raw)
            logger.info(f"Current:\n{obs.string()}")
        elif self.has_metar("summary"):
            logger.info(f"Current:\n{'\n'.join(self.metar.summary.split(','))}")

        # Print forecast
        taf = Taf(self.station.icao)
        if taf is not None:
            taf_updated = taf.update()
            if taf_updated and hasattr(taf, "summary"):
                if self.show == "nice":
                    taf_text = pytaf.Decoder(pytaf.TAF(taf.raw)).decode_taf()
                    # Split TAF in blocks of forecasts
                    forecast = []
                    prevision = []
                    for line in taf_text.split("\n"):
                        if len(line.strip()) > 0:
                            prevision.append(line)
                        else:
                            forecast.append(prevision)
                            prevision = []
                    # logger.info(f"Forecast:\n{taf_text}")
                    logger.info(f"Forecast:\n{'\n'.join(['\n'.join(t) for t in forecast])}")
                else:
                    logger.info(f"Forecast:\n{'\n'.join(taf.speech.split('.'))}")

    def needs_update(self) -> bool:
        # 1. No metar
        if self.metar is None:
            logger.debug(f"no metar")
            return True
        if self.metar.raw is None:
            logger.debug(f"no updated metar")
            return True
        # 2. METAR older that 30min
        if self._last_updated is None:
            logger.debug(f"never updated")
            return True
        now = datetime.now()
        diff = now.timestamp() - self._last_updated.timestamp()
        if diff > WeatherMetarIcon.MIN_UPDATE:
            logger.debug(f"expired")
            return True
        return False

    def update(self, force: bool = False) -> bool:
        """
        Creates or updates Metar. Call to avwx may fail, so it is wrapped into try/except block

        :param    force:  The force
        :type      force:  bool

        :returns:   { description_of_the_return_value }
        :rtype:  bool
        """
        self.inc("update")

        updated = False
        if force:
            self._last_updated = None

        new_station = self.get_station()

        if new_station is None:
            if self.station is None:
                return updated  # no new station, no existing station, we leave it as it is

        if self.station is None:
            try:
                self.station = new_station
                updated = self.update_metar(create=True)
                updated = True  # force
                self.sun = Sun(self.station.latitude, self.station.longitude)
                self.button._config["label"] = new_station.icao
                logger.info(f"UPDATED: new station {self.station.icao}")
            except:
                self.metar = None
                logger.warning(f"new station {new_station.icao}: Metar not created", exc_info=True)
        elif new_station is not None and new_station.icao != self.station.icao:
            try:
                old_station = self.station.icao
                self.station = new_station
                updated = self.update_metar(create=True)
                updated = True  # force
                self.sun = Sun(self.station.latitude, self.station.longitude)
                self.button._config["label"] = new_station.icao
                logger.info(f"UPDATED: station changed from {old_station} to {self.station.icao}")
            except:
                self.metar = None
                logger.warning(f"change station to {new_station.icao}: Metar not created", exc_info=True)
        elif self.metar is None:  # create it the first time
            try:
                updated = self.update_metar(create=True)
                updated = True  # force
                logger.info(f"UPDATED: station {self.station.icao}, first Metar")
            except:
                self.metar = None
                logger.warning(
                    f"station {self.station.icao}, first Metar not created",
                    exc_info=True,
                )
        else:
            try:
                now = datetime.now()
                if self._last_updated is None:
                    updated = self.update_metar()
                    logger.debug(f"station {self.station.icao}, Metar collected")
                else:
                    diff = now.timestamp() - self._last_updated.timestamp()
                    if diff > WeatherMetarIcon.MIN_UPDATE:
                        updated = self.update_metar()
                    else:
                        logger.debug(f"station {self.station.icao}, Metar does not need updating (last updated at {self._last_updated})")
            except:
                self.metar = None
                logger.warning(f"station {self.station.icao}: Metar not updated", exc_info=True)

        # if new is None, we leave it as it is
        if updated and self.station is not None:
            # AVWX's Metar is not as comprehensive as python-metar's Metar...
            if self.has_metar("data"):
                logger.debug(f"data for {self.station.icao}")
                self.weather_pressure.update_value(self.metar.data.altimeter.value)
                logger.debug(f"pressure {self.metar.data.altimeter.value}")
                self.weather_wind_speed.update_value(self.metar.data.wind_speed.value)
                logger.debug(f"wind speed {self.metar.data.wind_speed.value}")
                self.weather_temperature.update_value(self.metar.data.temperature.value)
                logger.debug(f"temperature {self.metar.data.temperature.value}")
                self.weather_dew_point.update_value(self.metar.data.dewpoint.value)
                logger.debug(f"dew point {self.metar.data.dewpoint.value}")
            else:
                logger.debug(f"no metar data for {self.station.icao}")
            self.weather_icon = self.select_weather_icon()
            logger.debug(f"Metar updated for {self.station.icao}, icon={self.weather_icon}, updated={updated}")
            self.inc("real update")

        return updated

    def get_image_for_icon(self):
        """
        Helper function to get button image and overlay label on top of it.
        Label may be updated at each activation since it can contain datarefs.
        Also add a little marker on placeholder/invalid buttons that will do nothing.
        """

        logger.debug(f"updating..")
        if self._busy_updating:
            logger.info(f"..updating in progress..")
            return
        self._busy_updating = True
        if not self.update() and self._cache is not None:
            logger.debug(f"..not updated, using cache")
            self._busy_updating = False
            return self._cache

        image = Image.new(mode="RGBA", size=(ICON_SIZE, ICON_SIZE), color=TRANSPARENT_PNG_COLOR)  # annunciator text and leds , color=(0, 0, 0, 0)
        draw = ImageDraw.Draw(image)
        inside = round(0.04 * image.width + 0.5)

        # Weather Icon
        icon_font = self._config.get("icon-font", WEATHER_ICON_FONT)
        icon_size = int(image.width / 2)
        icon_color = self.icon_color
        font = self.get_font(icon_font, icon_size)
        inside = round(0.04 * image.width + 0.5)
        w = image.width / 2
        h = image.height / 2
        logger.debug(f"weather icon: {self.weather_icon}")
        icon_text = WEATHER_ICONS.get(self.weather_icon)
        final_icon = self.weather_icon
        if icon_text is None:
            logger.warning(f"weather icon '{self.weather_icon}' not found, using default ({DEFAULT_WEATHER_ICON})")
            final_icon = DEFAULT_WEATHER_ICON
            icon_text = WEATHER_ICONS.get(DEFAULT_WEATHER_ICON)
            if icon_text is None:
                logger.warning(f"default weather icon {DEFAULT_WEATHER_ICON} not found, using hardcoded default (wi_day_sunny)")
                final_icon = "wi_day_sunny"
                icon_text = "\uf00d"
        logger.info(f"weather icon: {final_icon} ({self.speed})")
        draw.text(
            (w, h),
            text=icon_text,
            font=font,
            anchor="mm",
            align="center",
            fill=light_off(icon_color, 0.8),
        )  # (image.width / 2, 15)

        # Weather Data
        lines = None
        try:
            if self.has_metar("summary"):
                lines = self.metar.summary.split(",")  # ~ 6-7 short lines
        except:
            lines = None
            logger.warning(f"Metar has no summary")
            # logger.warning(f"get_image_for_icon: Metar has no summary", exc_info=True)

        if lines is not None:
            text, text_format, text_font, text_color, text_size, text_position = self.get_text_detail(self._representation_config, "weather")
            if text_font is None:
                text_font = self.label_font
            if text_size is None:
                text_size = int(image.width / 10)
            if text_color is None:
                text_color = self.label_color
            font = self.get_font(text_font, text_size)
            w = inside
            p = "l"
            a = "left"
            h = image.height / 3
            il = text_size
            for line in lines:
                draw.text(
                    (w, h),
                    text=line.strip(),
                    font=font,
                    anchor=p + "m",
                    align=a,
                    fill=text_color,
                )  # (image.width / 2, 15)
                h = h + il
        else:
            icao = self.station.icao if self.station is not None else "no station"
            logger.warning(f"no metar summary ({icao})")

        # Paste image on cockpit background and return it.
        bg = self.button.deck.get_icon_background(
            name=self.button_name(),
            width=ICON_SIZE,
            height=ICON_SIZE,
            texture_in=self.cockpit_texture,
            color_in=self.cockpit_color,
            use_texture=True,
            who="Weather",
        )
        bg.alpha_composite(image)
        self._cache = bg

        logger.debug(f"..updated")
        self._busy_updating = False
        return self._cache

    def has_metar(self, what: str = "raw"):
        if what == "summary":
            return self.metar is not None and self.metar.summary is not None
        elif what == "data":
            return self.metar is not None and self.metar.data is not None
        return self.metar is not None and self.metar.raw is not None

    def is_metar_day(self, sunrise: int = 6, sunset: int = 18) -> bool:
        if not self.has_metar():
            logger.debug("no metar, assuming day")
            return True
        time = self.metar.raw[7:12]
        logger.debug(f"zulu {time}")
        if time[-1] != "Z":
            logger.warning(f"no zulu? {time}")
            return True
        tz = self.get_timezone()
        logger.debug(f"timezone {'UTC' if tz == timezone.utc else tz.key}")
        utc = datetime.now(timezone.utc)
        utc = utc.replace(hour=int(time[0:2]), minute=int(time[2:4]))
        local = utc.astimezone(tz=tz)
        sun = self.get_sun(local)
        day = local.hour > sun[0] and local.hour < sun[1]
        logger.info(
            f"metar: {time}, local: {local.strftime('%H%M')} {tz} ({local.utcoffset()}), {'day' if day else 'night'} (sunrise {sun[0]}, sunset {sun[1]})"
        )
        return day

    def is_day(self, sunrise: int = 5, sunset: int = 19) -> bool:
        # Uses the simulator local time
        hours = self.button.get_simulator_data_value("sim/cockpit2/clock_timer/local_time_hours", default=12)
        if self.sun is not None:
            sr = self.sun.get_sunrise_time()
            ss = self.sun.get_sunset_time()
        else:
            sr = sunrise
            ss = sunset
        return hours >= sr and hours <= ss

    def get_timezone(self):
        # pip install timezonefinder
        # from zoneinfo import ZoneInfo
        # from timezonefinder import TimezoneFinder
        #
        tf = TimezoneFinder()
        tzname = tf.timezone_at(lng=self.station.longitude, lat=self.station.latitude)
        if tzname is not None:
            logger.debug(f"timezone is {tzname}")
            return ZoneInfo(tzname)
        logger.debug(f"no timezone, using utc")
        return timezone.utc

    def get_sunrise_time(self):
        # pip install timezonefinder
        # from zoneinfo import ZoneInfo
        # from timezonefinder import TimezoneFinder
        #
        tf = TimezoneFinder()
        tzname = tf.timezone_at(lng=self.station.longitude, lat=self.station.latitude)
        if tzname is not None:
            return ZoneInfo(tzname)
        return timezone.utc

    def get_sun(self, moment: datetime | None = None):
        # Returns sunrise and sunset rounded hours (24h)
        if moment is None:
            today_sr = self.sun.get_sunrise_time()
            today_ss = self.sun.get_sunset_time()
            return (today_sr.hour, today_ss.hour)
        today_sr = self.sun.get_sunrise_time(moment)
        today_ss = self.sun.get_sunset_time(moment)
        return (today_sr.hour, today_ss.hour)

    def day_night(self, icon, day: bool = True):
        # Selects day or night variant of icon
        logger.debug(f"search {icon}, {day}")

        # Special case cavok
        if icon == KW_CAVOK:
            logger.debug(f"{KW_CAVOK}, {day}")
            return CAVOK_DAY if day else CAVOK_NIGHT

        # Do we have a variant?
        icon_np = icon.replace("wi_", "")
        try_icon = None
        dft_name = None
        for prefix in [
            WI_PREFIX,
            WI_PREFIX + DAY,
            WI_PREFIX + NIGHT,
            WI_PREFIX + NIGHT_ALT,
        ]:
            if try_icon is None:
                dft_name = prefix + icon_np
                logger.debug(f"trying {dft_name}..")
                try_icon = WEATHER_ICONS.get(dft_name)
        if try_icon is None:
            logger.debug(f"no such icon or variant {icon}")
            return DEFAULT_WEATHER_ICON
        else:
            logger.debug(f"exists {dft_name}")

        # From now on, we are sure we can find an icon
        # day
        if not day:
            icon_name = WI_PREFIX + NIGHT + icon
            try_icon = WEATHER_ICONS.get(icon_name)
            if try_icon is not None:
                logger.debug(f"exists night {icon_name}")
                return icon_name

            icon_name = WI_PREFIX + NIGHT_ALT + icon
            try_icon = WEATHER_ICONS.get(icon_name)
            if try_icon is not None:
                logger.debug(f"exists night-alt {try_icon}")
                return icon_name

        icon_name = WI_PREFIX + DAY + icon
        try_icon = WEATHER_ICONS.get(icon_name)
        if try_icon is not None:
            logger.debug(f"exists day {icon_name}")
            return icon_name

        logger.debug(f"found {dft_name}")
        return dft_name

    def select_weather_icon(self):
        # Needs improvement
        # Stolen from https://github.com/flybywiresim/efb
        icon = "wi_cloud"
        if self.has_metar():
            rawtext = self.metar.raw[13:]  # strip ICAO DDHHMMZ
            logger.debug(f"METAR {rawtext}")
            # Precipitations
            precip = re.match("RA|SN|DZ|SG|PE|GR|GS", rawtext)
            if precip is None:
                precip = []
            logger.debug(f"PRECIP {precip}")
            # Wind
            wind = self.metar.data.wind_speed.value if hasattr(self.metar.data, "wind_speed") else 0
            logger.debug(f"WIND {wind}")

            findIcon = []
            for item in WI.DB:
                t1 = reduce(
                    lambda x, y: x + y,
                    [rawtext.find(desc) for desc in item[KW_TAGS]],
                    0,
                ) == len(item[KW_TAGS])
                t_precip = (len(item[KW_PRECIP]) == 0) or rawtext.find(item[KW_PRECIP])
                t_clouds = (
                    (len(item[KW_CLOUD]) == 0)
                    or (len(item[KW_CLOUD]) == 1 and item[KW_CLOUD][0] == "")
                    or (
                        reduce(
                            lambda x, y: x + y,
                            [rawtext.find(cld) for cld in item[KW_CLOUD]],
                            0,
                        )
                        > 0
                    )
                )
                t_wind = wind > item[KW_WIND][0] and wind < item[KW_WIND][1]
                t_vis = (len(item[KW_VIS]) == 0) or (
                    reduce(
                        lambda x, y: x + y,
                        [rawtext.find(vis) for vis in item[KW_VIS]],
                        0,
                    )
                    > 0
                )
                ok = t1 and t_precip and t_clouds and t_wind and t_vis
                if ok:
                    findIcon.append(item)
                logger.debug(f"findIcon: {item[KW_NAME]}, list={t1}, precip={t_precip}, clouds={t_clouds}, wind={t_wind}, vis={t_vis} {('<'*10) if ok else ''}")
            logger.debug(f"STEP 1 {findIcon}")

            # findIcon = list(filter(lambda item: reduce(lambda x, y: x + y, [rawtext.find(desc) for desc in item[KW_TAGS]], 0) == len(item[KW_TAGS])
            #                            and ((len(item[KW_PRECIP]) == 0) or rawtext.find(item[KW_PRECIP]))
            #                            and ((len(item[KW_CLOUD]) == 0) or (len(item[KW_CLOUD]) == 1 and item[KW_CLOUD][0] == "") or (reduce(lambda x, y: x + y, [rawtext.find(cld) for cld in item[KW_CLOUD]], 0) > 0))
            #                            and (wind > item[KW_WIND][0] and wind < item[KW_WIND][1])
            #                            and ((len(item[KW_VIS]) == 0) or (reduce(lambda x, y: x + y, [rawtext.find(vis) for vis in item[KW_VIS]], 0) > 0)),
            #                  WI.DB))
            # logger.debug(f"STEP 1 {findIcon}")

            l = len(findIcon)
            if l == 1:
                icon = findIcon[0]["iconName"]
            else:
                if l > 1:
                    findIcon2 = []
                    if len(precip) > 0:
                        findIcon2 = list(
                            filter(
                                lambda x: re("RA|SN|DZ|SG|PE|GR|GS").match(x["precip"]),
                                findIcon,
                            )
                        )
                    else:
                        findIcon2 = list(filter(lambda x: x["day"] == day, findIcon))
                    logger.debug(f"STEP 2 {findIcon2}")
                    if len(findIcon2) > 0:
                        icon = findIcon2[0]["iconName"]
        else:
            logger.debug(f"no metar ({self.metar})")

        logger.debug(f"weather icon {icon}")
        day = self.is_metar_day()
        daynight_icon = self.day_night(icon, day)
        if daynight_icon is None:
            logger.warning(f"no icon, using default {DEFAULT_WEATHER_ICON}")
            daynight_icon = DEFAULT_WEATHER_ICON
        daynight_icon = daynight_icon.replace("-", "_")  # ! Important
        logger.debug(f"day/night version: {day}: {daynight_icon}")
        return daynight_icon

    def select_random_weather_icon(self):
        # day or night
        # cloud cover
        # precipitation: type, quantity
        # wind: speed
        # currently random anyway...
        return random.choice(list(WEATHER_ICONS.values()))
