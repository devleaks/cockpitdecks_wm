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
from __future__ import annotations
import logging
import random
import re
import math
from functools import reduce
from datetime import datetime, date, timezone

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
from cockpitdecks.simulator import SimulatorVariable, SimulatorVariableListener

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


class WeatherMetarIcon(DrawAnimation, SimulatorVariableListener):
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
        self.previous_metars = []
        self.taf: Taf | None = None
        self.previous_tafs = []
        self.show = self.weather.get("summary")

        self.weather_icon: str | None = None
        self.update_position = False

        self.icao_dataref_path = button._config.get("string-dataref")
        self.icao_dataref = None

        DrawAnimation.__init__(self, button=button)
        SimulatorVariableListener.__init__(self)

        # "Animation" (refresh)
        speed = self.weather.get("refresh", 30)  # minutes, should be ~30 minutes
        self.speed = int(speed) * 60  # minutes

        self.icon_color = self.weather.get("icon-color", self.get_attribute("text-color"))
        self._no_coord_warn = 0

        # Plot defaults
        self.plot_style = "bw"  # | "color"
        self.plot_color = "black"
        self.barb_color = (160, 160, 160)
        self.text_color = "black"
        self.text_alt_color = "grey"
        self.text_past_color = "blue"
        self.plot_inverse = "white"  # | self.icon_color
        self.plot_text_font = "B612-Regular.ttf"
        self.plot_wmo_font = "wx_symbols.ttf"
        # for color plot (experimental)
        self.info_color = "blue"
        self.warn_color = "darkorange"
        self.alert_color = "red"
        self.good_color = "lime"
        self.disabled_color = "grey"

    def init(self):
        if self._inited:
            return

        # Initialize datarefs to communicate weather main parameters
        self.weather_pressure = self.button.sim.get_internal_variable("weather:pressure")
        self.weather_wind_speed = self.button.sim.get_internal_variable("weather:wind_speed")
        self.weather_temperature = self.button.sim.get_internal_variable("weather:temperature")
        self.weather_dew_point = self.button.sim.get_internal_variable("weather:dew_point")

        if self.icao_dataref_path is not None:
            # toliss_airbus/flightplan/departure_icao
            # toliss_airbus/flightplan/destination_icao
            self.icao_dataref = self.button.sim.get_variable(self.icao_dataref_path, is_string=True)
            self.icao_dataref.add_listener(self)  # the representation gets notified directly.
            self.simulator_variable_changed(self.icao_dataref)
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

    # #############################################
    # Cockpitdecks Representation interface
    #
    def get_simulator_variable(self) -> set:
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

    def simulator_variable_changed(self, data: SimulatorVariable):
        # what if Dataref.internal_variableref_path("weather:*") change?
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

    def get_image_for_icon(self):
        if self._busy_updating:
            logger.info(f"..updating in progress..")
            return
        self._busy_updating = True
        logger.debug("updating..")

        if self.show in ["taf", "forecast"]:
            return self.get_taf_image_for_icon()
        if self.show in ["surface-station-plot", "plot"]:
            return self.get_surface_station_plot_image_for_icon()
        return self.get_metar_image_for_icon()

    # Icon types: Metar text, Taf text, Station Plot
    def get_metar_image_for_icon(self):
        """
        Helper function to get button image and overlay label on top of it.
        Label may be updated at each activation since it can contain datarefs.
        Also add a little marker on placeholder/invalid buttons that will do nothing.
        """
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
        )

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
                )
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

    def get_taf_image_for_icon(self):
        """
        Helper function to get button image and overlay label on top of it.
        Label may be updated at each activation since it can contain datarefs.
        Also add a little marker on placeholder/invalid buttons that will do nothing.
        """
        bv = self.button.value
        if bv is None:
            bv = 0
        else:
            bv = int(bv)
        bv = bv % 48.0  # hours

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
        )

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
                )
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

    def get_surface_station_plot_image_for_icon(self):
        # See:
        # https://geo.libretexts.org/Bookshelves/Meteorology_and_Climate_Science/Practical_Meteorology_(Stull)/09%3A_Weather_Reports_and_Map_Analysis/9.02%3A_Synoptic_Weather_Maps
        # https://en.wikipedia.org/wiki/Station_model

        if not self.update() and self._cache is not None:
            logger.debug(f"..not updated, using cache")
            self._busy_updating = False
            return self._cache

        logger.setLevel(logging.DEBUG)
        image = Image.new(mode="RGBA", size=(ICON_SIZE, ICON_SIZE), color=TRANSPARENT_PNG_COLOR)  # annunciator text and leds , color=(0, 0, 0, 0)

        if not self.has_metar():
            logger.warning(f"no metar")
            self._cache = image
            self._busy_updating = False
            return self._cache

        draw = ImageDraw.Draw(image)

        PLOT_SIZE = ICON_SIZE  # 100% fit icon
        inside = round(0.04 * image.width + 0.5)
        S12 = int(PLOT_SIZE / 2)  # half the size, the middle

        cellsize = int(PLOT_SIZE / 5)
        textfont = self.get_font(self.plot_text_font, int(PLOT_SIZE / 10))
        textfont_small = self.get_font(self.plot_text_font, int(PLOT_SIZE / 12))
        wmofont = self.get_font(self.plot_wmo_font, int(PLOT_SIZE / 7))
        wmofont_small = self.get_font(self.plot_wmo_font, int(PLOT_SIZE / 11))

        def pd(s):
            # logger.debug("*" * 30 + s)
            pass

        def cell_center(x, y):
            return (
                cellsize * (x - 0.5),
                cellsize * (y - 0.5),
            )

        station_plot_data = self.collect_station_plot_data()

        # #########################
        # DRAW procedure
        #
        # left:
        #
        def draw_temperature():
            temp = station_plot_data["temperature"]
            if temp is None:
                return
            text = f"{round(temp, 1):4.1f}"
            pd(f"draw_temperature: {temp}, {text}")
            draw.text(
                cell_center(2, 2),
                text=text,
                font=textfont,
                anchor="mm",
                align="center",
                fill=self.text_color,
            )

        def draw_visibility():
            vis = station_plot_data["visibility"]
            if vis is None:
                return
            viscode = vis
            if vis <= 5.5:
                viscode = vis * 10
            elif 5.5 < vis <= 30:
                viscode = vis + 50
            else:  # vis > 30
                viscode = vis / 5 + 74
            text = str(round(viscode))
            pd(f"draw_visibility: {vis}, {viscode}, {text}")
            draw.text(
                cell_center(1, 3),
                text=text,
                font=textfont,
                anchor="mm",
                align="center",
                fill=self.text_color,
            )

        def draw_current_weather_code():
            code = station_plot_data["current_weather_code"]
            if code is None:
                return
            pd(f"draw_current_weather_code: {code}, {int(code)}, {len(current_weather)}")
            text = current_weather.alt_char(code=int(code), alt=0)
            pd(f"draw_current_weather_code: {code}, {int(code)}, {len(current_weather)}, {text}")
            if text is None:
                logger.warning(f"current_weather: {int(code)} leads to invalid character")
                return
            draw.text(
                cell_center(2, 3),
                text=text,
                font=wmofont,
                anchor="mm",
                align="center",
                fill=self.text_color,
            )

        def draw_dew_point():
            temp = station_plot_data["dew_point"]
            if temp is None:
                return
            text = f"{round(temp, 1):4.1f}"
            pd(f"draw_dew_point: {temp}, {text}")
            draw.text(
                cell_center(2, 4),
                text=text,
                font=textfont,
                anchor="mm",
                align="center",
                fill=self.text_color,
            )

        def draw_sea_surface():
            temp = station_plot_data["sea_surface"]
            if temp is None:
                return
            text = f"{round(temp, 1):4.1f}"
            pd(f"draw_sea_surface: {temp}, {text}")
            draw.text(
                cell_center(2, 5),
                text=text,
                font=textfont,
                anchor="mm",
                align="center",
                fill=self.text_alt_color,
            )

        #
        # center:
        #
        def draw_high_clouds():
            clouds = station_plot_data["high_clouds"]
            if clouds is None:
                return
            pd(f"draw_high_clouds: {clouds}, {len(high_clouds)}")
            text = high_clouds.alt_char(code=int(clouds), alt=0)
            pd(f"draw_high_clouds: {clouds}, {text}")
            if text is None:
                logger.warning(f"high_clouds code {clouds} leads to invalid character")
                return
            draw.text(
                cell_center(3, 1),
                text=text,
                font=wmofont,
                anchor="mm",
                align="center",
                fill=self.text_color,
            )

        def draw_middle_clouds():
            clouds = station_plot_data["mid_clouds"]
            if clouds is None:
                return
            pd(f"draw_middle_clouds: {clouds}, {int(clouds)}, {len(mid_clouds)}")
            text = mid_clouds.alt_char(code=int(clouds), alt=0)
            pd(f"draw_middle_clouds: {clouds}, {int(clouds)}, {text}")
            if text is None:
                logger.warning(f"mid_clouds code {int(clouds)} leads to invalid character")
                return
            draw.text(
                cell_center(3, 2),
                text=text,
                font=wmofont,
                anchor="mm",
                align="center",
                fill=self.text_color,
            )

        def draw_total_sky_cover():
            coverage = station_plot_data["sky_cover"]
            radius = int(PLOT_SIZE / 12)
            width = 3
            bbox = (S12 - radius, S12 - radius, S12 + radius, S12 + radius)
            draw.ellipse(bbox, width=width, outline=self.plot_color)
            if coverage is None:
                pd(f"draw_total_sky_cover: no coverage")
                return
            covidx = int(coverage / 0.125) + 1
            pd(f"draw_total_sky_cover: {round(coverage, 3)} index {covidx}")
            if covidx == 0:
                return
            if covidx in [2, 3]:
                draw.pieslice(bbox, -90, 0, fill=self.plot_color)
                if covidx == 2:
                    return
            if covidx in [1, 3]:
                draw.line([(S12, S12 - radius), (S12, S12 + radius)], width=width, fill=self.plot_color)
                return
            if covidx in [4, 5]:
                draw.pieslice(bbox, -90, 90, fill=self.plot_color)
                if covidx == 4:
                    return
                draw.line([(S12, S12 - radius), (S12, S12 + radius)], width=width, fill=self.plot_color)
                return
            if covidx == 6:
                draw.pieslice(bbox, -90, 180, fill=self.plot_color)
                return
            draw.ellipse(bbox, fill=self.plot_color)
            if covidx == 7:
                draw.line([(S12, S12 - radius), (S12, S12 + radius)], width=2 * width, fill=self.plot_inverse)

        def draw_low_clouds():
            thiscell = cell_center(3, 4)
            shift = 16
            # 1. Cloud type
            clouds = station_plot_data["low_clouds"]
            if clouds is None:
                return
            pd(f"draw_low_clouds: {clouds}, {len(low_clouds)}")
            text = low_clouds.alt_char(code=int(clouds), alt=0)
            pd(f"draw_low_clouds: {clouds}, {text}")
            if text is None:
                logger.warning(f"low_clouds code {clouds} leads to invalid character")
                return
            draw.text((thiscell[0] - shift, thiscell[1] - int(shift / 2)), text=text, font=wmofont_small, anchor="mm", align="center", fill=self.text_color)
            # 2. Cloud coverage (/8)
            coverage = station_plot_data["low_clouds_cover"]
            if coverage is None:
                return
            covidx = int(coverage / 0.125) + 1
            pd(f"draw_low_clouds/coverage: {coverage}, {covidx}, {len(sky_cover)}")
            text = sky_cover.alt_char(code=covidx, alt=0)
            pd(f"draw_low_clouds/coverage: {coverage}, {covidx}, {text}")
            if text is None:
                logger.warning(f"sky_cover code {covidx} leads to invalid character")
                return
            draw.text((thiscell[0] + shift, thiscell[1] - int(shift / 2)), text=text, font=wmofont_small, anchor="mm", align="center", fill=self.text_color)
            # 3. Low cloud base height (in flight level)
            height = station_plot_data["low_clouds_base_m"]
            if height is None:
                return
            text = 0
            if 50 < height < 100:
                text = 1
            elif 100 <= height < 200:
                text = 2
            elif 200 <= height < 300:
                text = 3
            elif 300 <= height < 600:
                text = 4
            elif 600 <= height < 1000:
                text = 5
            elif 1000 <= height < 1500:
                text = 6
            elif 1500 <= height < 2000:
                text = 7
            elif 2000 <= height < 2500:
                text = 8
            elif 2500 <= height:
                text = 9
            text = str(text)
            pd(f"draw_low_clouds/height: {height}, {text}")
            draw.text((thiscell[0], thiscell[1] + shift), text=text, font=textfont, anchor="mm", align="center", fill=self.text_color)

        def draw_wind_barbs():
            speed, direction, gust = station_plot_data["wind"]
            # rounds direction to quarter cardinals N-NE
            steps = 22.5  # °

            pd(f"draw_wind_barbs: speed {round(speed, 1)}, {round(direction, 1) if direction is not None else '---'}")
            wind_image = Image.new(mode="RGBA", size=(PLOT_SIZE, PLOT_SIZE), color=TRANSPARENT_PNG_COLOR)  # annunciator text and leds , color=(0, 0, 0, 0)
            wd = ImageDraw.Draw(wind_image)

            numbars = 8
            barbwidth = 3
            barlength = int(PLOT_SIZE / 3)
            slant = int(PLOT_SIZE / 32)
            barstep = int(barlength / numbars)
            barend = S12 + barlength

            triheight = int(PLOT_SIZE / 8)

            if speed is None:
                if direction is not None:
                    # just a bar to indicate wind direction?
                    wd.line([(S12, S12), (S12, barend)], width=barbwidth, fill=self.barb_color)
                    wind_image = wind_image.rotate(angle=direction + 180)
                    image.alpha_composite(wind_image)
                return

            totspeed = speed

            if totspeed < 5:
                radius = int(PLOT_SIZE / 12) + 8
                bbox = (S12 - radius, S12 - radius, S12 + radius, S12 + radius)
                draw.ellipse(bbox, width=barbwidth, outline=self.barb_color)
            else:
                wd.line([(S12, S12), (S12, barend)], width=barbwidth, fill=self.barb_color)
                # Draw triangles for 50kn
                while totspeed > 50:
                    first = (S12, barend)
                    barend = barend - barstep
                    second = (S12, barend)
                    top = (S12 + triheight, barend + barstep / 2 + slant)
                    wd.polygon([first, second, top, first], fill=self.barb_color)
                    totspeed = totspeed - 50
                # Draw long bar for 50kn
                while totspeed > 10:
                    start = (S12, barend)
                    end = (S12 + triheight, barend + slant)
                    wd.line([start, end], width=barbwidth, fill=self.barb_color)
                    barend = barend - barstep
                    totspeed = totspeed - 10
                # Draw short bar for 5kn
                while totspeed > 5:
                    start = (S12, barend)
                    end = (S12 + triheight / 2, barend + slant / 2)
                    wd.line([start, end], width=barbwidth, fill=self.barb_color)
                    barend = barend - barstep
                    totspeed = totspeed - 5

                if direction is not None:
                    direction = steps * round(direction / steps)
                    wind_image = wind_image.rotate(angle=direction + 180)
                else:
                    wind_image = wind_image.rotate(angle=90)
                    # Move windbar out of drawing (bottom)
                    a = 1
                    b = 0
                    c = int(PLOT_SIZE / 4)  # left/right, x
                    d = 0
                    e = 1
                    f = -int(15 * PLOT_SIZE / 32)  # up/down, y
                    wind_image = wind_image.transform(image.size, Image.AFFINE, (a, b, c, d, e, f))

            if gust is not None:
                text = f"{round(gust):3d}"
                pd(f"draw_wind_barbs: gust: {gust}, {text}")
                if direction is not None:
                    x = S12 + (barlength + 4) * math.sin(math.radians(direction + 180))
                    y = S12 + (barlength + 4) * math.cos(math.radians(direction + 180))
                else:  # not correct
                    x = PLOT_SIZE - int(PLOT_SIZE / 4)
                    y = PLOT_SIZE - int(PLOT_SIZE / 16)
                draw.text((x, y), text=text, font=textfont_small, anchor="mm", align="center", fill="red")  # self.text_color,

            image.alpha_composite(wind_image)

        def draw_waves():
            wave, period = station_plot_data["waves"]
            if wave is None or period is None:
                pd(f"draw_waves: no info")
                return
            text = f"{round(wave, 1):4.1f}\n{round(period, 1):4.1f}"
            pd(f"draw_waves: {wave}, {period}, {text}")
            draw.text(
                cell_center(3, 5),
                text=text,
                font=textfont_small,
                anchor="mm",
                align="center",
                fill=self.text_alt_color,
            )

        #
        # right:
        #
        def draw_pressure():
            press = station_plot_data["pressure"]
            if press is None:
                return
            text = str(int(round(press * 10, 0)))[-3:]  # decaPascal, not HectoPascal
            pd(f"draw_pressure: {press}, {str(int(round(press, 1)))}, {text}")
            draw.text(
                cell_center(4, 2),
                text=text,
                font=textfont,
                anchor="mm",
                align="center",
                fill=self.text_color,
            )

        def draw_pressure_change():
            press = station_plot_data["pressure_change"]
            if press is None:
                return
            # if press == 0:
            #     return
            text = str(int(round(press * 10, 0)))[-3:]  # decaPascal, not HectoPascal
            pd(f"draw_pressure_change: {press}, {str(int(round(press, 1)))}, {text}")
            draw.text(
                cell_center(4, 3),
                text=text,
                font=textfont,
                anchor="mm",
                align="center",
                fill=self.text_color,
            )

        def draw_pressure_change_trend():
            code = station_plot_data["pressure_trend"]
            if code is None:
                return
            # text = "\uE908"
            pd(f"draw_pressure_change_trend: {code}, {len(pressure_tendency)}")
            text = pressure_tendency.alt_char(code=int(code), alt=0)
            pd(f"draw_pressure_change_trend: {code}, {text}")
            if text != "":
                draw.text(
                    cell_center(5, 3),
                    text=text,
                    font=wmofont,
                    anchor="mm",
                    align="center",
                    fill=self.text_color,
                )

        def draw_obs_utc():
            press = station_plot_data["obs_utc"]
            if press is None:
                return
            text = press.strftime("%H:%M")
            pd(f"draw_obs_utc: {press.isoformat()}, {text}")
            draw.text(
                cell_center(5, 4),
                text=text,
                font=textfont_small,
                anchor="mm",
                align="center",
                fill=self.text_alt_color,
            )

        def draw_past_weather_code():
            code = station_plot_data["past_weather_code"]
            if code is None:
                pd("draw_past_weather_code: no code")
                return

            pd(f"draw_past_weather_code: {code} {len(current_weather)}")
            text = current_weather.alt_char(code=int(code), alt=0)
            if text is None:
                logger.warning(f"current_weather code {code} leads to invalid character")
                return
            pd(f"draw_past_weather_code: {code}, {text}")
            if text != "":
                draw.text(
                    cell_center(4, 4),
                    text=text,
                    font=wmofont,
                    anchor="mm",
                    align="center",
                    fill=self.text_past_color,
                )

        def draw_precipitation_last_time():
            prec, lasttime = station_plot_data["past_precipitations"]
            if prec is None:
                return
            if prec == 0:
                return
            text = f"{round(prec)}/{round(lasttime)}"
            pd(f"draw_precipitation_last_time: {prec}, {lasttime}, {text}")
            draw.text(
                cell_center(4, 5),
                text=text,
                font=textfont,
                anchor="mm",
                align="center",
                fill=self.text_past_color,
            )

        def draw_six_hour_precipitation_forecast():
            prec, forecast = station_plot_data["forecast_precipitations"]
            if prec is None:
                return
            if prec == 0:
                return
            text = f"{round(prec)}/{round(forecast)}"
            pd(f"draw_precipitation_last_time: {prec}, {forecast}, {text}")
            draw.text(
                cell_center(5, 5),
                text=text,
                font=textfont,
                anchor="mm",
                align="center",
                fill=self.text_color,
            )

        # #########################
        # DRAW!
        #
        # center, ~base
        draw_wind_barbs()
        draw_total_sky_cover()
        # left
        draw_temperature()
        draw_visibility()
        draw_current_weather_code()
        draw_dew_point()
        draw_sea_surface()
        # center
        draw_high_clouds()
        draw_middle_clouds()
        draw_low_clouds()
        draw_waves()
        # right
        draw_pressure()
        draw_pressure_change()
        draw_pressure_change_trend()
        draw_obs_utc()
        draw_past_weather_code()
        draw_precipitation_last_time()
        draw_six_hour_precipitation_forecast()

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

        logger.debug(f"..plot updated")
        logger.setLevel(logging.INFO)
        self._busy_updating = False
        # self._cache = bg
        # return self._cache
        return bg  # for debugging purpose

    # #############################################
    # Metar update and utility function
    # - because time update
    # - because station changed (because aircraft movement)
    #
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
        lat = self.button.get_simulator_variable_value("sim/flightmodel/position/latitude")
        lon = self.button.get_simulator_variable_value("sim/flightmodel/position/longitude")

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

    def at_default_station(self):
        ret = True
        if self.weather is not None and self.station is not None:
            ret = not self._moved and self.station.icao == self.weather.get("station", WeatherMetarIcon.DEFAULT_STATION)
            logger.debug(
                f"currently at {self.station.icao}, default station {self.weather.get('station', WeatherMetarIcon.DEFAULT_STATION)}, moved={self._moved}, returns {ret}"
            )
        return ret

    def has_metar(self, what: str = "raw"):
        if what == "summary":
            return self.metar is not None and self.metar.summary is not None
        elif what == "data":
            return self.metar is not None and self.metar.data is not None
        return self.metar is not None and self.metar.raw is not None

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

    def update_metar(self, create: bool = False):
        if create:
            self.metar = Metar(self.station.icao)
            self.taf = Taf(self.station.icao)
        if not self.needs_update():
            return False
        before = self.metar.raw
        updated = self.metar.update()  # this should be the only place where the Metar/Taf gets updated
        dummy = self.taf.update()
        self._last_updated = datetime.now()
        if updated:
            if before is not None:
                self.previous_metars.append(before)
                self.previous_tafs.append(self.taf.raw)
            logger.info(f"station {self.station.icao}, Metar updated")
            logger.info(f"update: {before} -> {self.metar.raw}")
            if self.show is not None:
                self.print()
        else:
            logger.info(f"station {self.station.icao}, Metar fetched, unchanged")
        return updated

    def is_metar_valid(self, metar: str) -> bool:
        try:
            m = Metar.from_report(report=metar, issued=date.today())
            return True
        except:
            logger.warning(f"invalid metar {metar}", exc_info=True)
        return False

    def get_utc(self, metar: str) -> bool:
        try:
            m = Metar.from_report(metar)
            t = m.data.time  # !! this is a special AVWX Timestamp class, not python standard Timestamp !!
            if t is not None:
                return t.dt
            return None
        except:
            logger.warning(f"invalid metar {metar}", exc_info=True)
        return None

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

    def print(self):
        # Print current situation
        if self.has_metar("raw") and self.show == "nice":
            obs = MetarDesc.Metar(self.metar.raw)
            logger.info(f"Current:\n{obs.string()}")
        elif self.has_metar("summary"):
            logger.info(f"Current:\n{'\n'.join(self.metar.summary.split(','))}")

        # Print forecast
        taf = self.taf if self.taf is not None else Taf(self.station.icao)
        if taf is not None:
            taf_updated = taf.update()
            if taf_updated and hasattr(taf, "summary"):
                if self.show in ["nice", "taf"]:
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

    # Time-related Metars
    # Past
    def get_metar_for(self, icao: str) -> list:
        return filter(lambda m: m.startswith(icao), self.previous_metars)

    def get_older_metar(self, icao: str) -> list:
        candidates = self.get_metar_for(icao=icao)
        return candidates

    # Future
    def get_taf_for(self, icao: str) -> list:
        return filter(lambda m: m.startswith(icao), self.previous_tafs)

    def has_trend(self) -> bool:
        if len(self.previous_metars) > 0 and self.metar is not None and hasattr(self.metar, "raw"):
            last = self.previous_metars[-1]
            if last is None:
                return False
            return last[:4] == self.metar.raw[:4]  # same station
        return False

    def collect_station_plot_data(self, at_random: bool = False) -> dict:
        # #########################
        # Information/value collection procedures
        #
        # left:
        def get_plot_temperature():
            return random.random() * 50 - 15

        def get_plot_visibility():
            return random.random() * 120

        def get_plot_current_weather_code():
            weather = [random.choice(list(CodePointMapping.wx_code_map.keys()))]
            codes = wx_code_to_numeric(weather)
            return codes[0] if len(codes) > 0 else None  # random.random() * len(current_weather)

        def get_plot_dew_point():
            return -5 + random.random() * 10

        def get_plot_sea_surface():
            return 10 + random.random() * 10

        # center:
        def get_plot_high_clouds():
            return random.random() * len(high_clouds)

        def get_plot_middle_clouds():
            return random.random() * len(mid_clouds)

        def get_plot_total_sky_cover():
            return random.random()

        def get_plot_low_clouds():
            return random.random() * len(low_clouds)

        def get_plot_low_clouds_cover():
            return random.random()

        def get_plot_low_clouds_height():
            return random.random() * 3000  # ft?

        def get_plot_waves():
            return (random.random() * 5, random.random() * 30)

        def get_plot_wind():
            return (
                random.random() * 120,
                random.random() * 360 if random.random() > 0.5 else None,
                random.random() * 80 if random.random() > 0.5 else None,
            )

        # right:
        def get_plot_pressure():
            return 975 + random.random() * 60

        def get_plot_pressure_change():
            return -2 + random.random() * 4

        def get_plot_pressure_change_trend():
            return random.random() * len(pressure_tendency)

        def get_plot_obs_utc():
            return datetime.now()

        def get_plot_past_weather_code():
            weather = [random.choice(list(CodePointMapping.wx_code_map.keys()))]
            codes = wx_code_to_numeric(weather)
            return codes[0] if len(codes) > 0 else None  # random.random() * len(current_weather)

        def get_plot_precipitation_last_time():
            return (random.random() * 2, random.random() * 5)

        def get_plot_six_hour_precipitation_forewast():
            return (random.random() * 2, random.random() * 5)

        # code modifiers
        def is_vicinity():
            return random.random() > 0.5

        def get_intensity():
            return random.choice(["light", "moderate", "heavy"])

        def is_intermittent():
            return random.random() > 0.5

        def is_virga():
            return random.random() > 0.5

        def is_past_hour_not_now():
            return random.random() > 0.5

        def is_past_hour_and_now():
            return random.random() > 0.5

        def is_decreased_past_hour_occuring_now():
            return random.random() > 0.5

        # #########################
        # Compilation
        #
        is_valid = self.is_metar_valid(metar=self.metar.raw)
        if is_valid:
            utc = self.get_utc(metar=self.metar.raw)
            logger.info(f"METAR: {self.metar.raw}, utc={utc}")
        no = "" if self.has_trend() else "no "
        logger.info(f"has {no}trend")

        logger.warning("using random weather for station plot display")
        station_plot_data = {
            "temperature": get_plot_temperature(),
            "visibility": get_plot_visibility(),
            "current_weather_code": get_plot_current_weather_code(),
            "dew_point": get_plot_dew_point(),
            "sea_surface": get_plot_sea_surface(),
            "waves": get_plot_waves(),
            "high_clouds": get_plot_high_clouds(),
            "mid_clouds": get_plot_middle_clouds(),
            "sky_cover": get_plot_total_sky_cover(),
            "low_clouds": get_plot_low_clouds(),
            "low_clouds_cover": get_plot_low_clouds_cover(),
            "low_clouds_base_m": get_plot_low_clouds_height(),
            "wind": get_plot_wind(),  # kn?
            "pressure": get_plot_pressure(),
            "pressure_change": get_plot_pressure_change(),
            "pressure_trend": get_plot_pressure_change_trend(),
            "past_weather_code": get_plot_past_weather_code(),
            "past_precipitations": get_plot_precipitation_last_time(),
            "forecast_precipitations": get_plot_six_hour_precipitation_forewast(),
            "vicinity": is_vicinity(),
            "intensity": get_intensity(),
            "virga": is_virga(),
            "past_hour_not_now": is_past_hour_not_now(),
            "past_hour_and_now": is_past_hour_and_now(),
            "decreased_past_hour_occuring_now": is_decreased_past_hour_occuring_now(),
            "obs_utc": get_plot_obs_utc(),
        }

        # def random_weather():
        #     weather = [random.choice(list(CodePointMapping.wx_code_map.keys()))]
        #     codes = wx_code_to_numeric(weather)
        #     # print(">>>", weather, codes)
        #     return codes[0] if len(codes) > 0 else None  # random.random() * len(current_weather)
        # station_plot_data = {
        #     "temperature": random.random() * 50 - 15,
        #     "visibility": random.random() * 120,
        #     "current_weather_code": random_weather(),
        #     "dew_point": -5 + random.random() * 10,
        #     "sea_surface": 10 + random.random() * 10,
        #     "waves": (random.random() * 5, random.random() * 30),
        #     "high_clouds": random.random() * len(high_clouds),
        #     "mid_clouds": random.random() * len(mid_clouds),
        #     "sky_cover": random.random(),
        #     "low_clouds": random.random() * len(low_clouds),
        #     "low_clouds_cover": random.random(),
        #     "low_clouds_base_m": random.random() * 3000,
        #     "wind": (
        #         random.random() * 120,
        #         random.random() * 360 if random.random() > 0.5 else None,
        #         random.random() * 80 if random.random() > 0.5 else None,
        #     ),  # kn?
        #     "pressure": 975 + random.random() * 60,
        #     "pressure_change": -2 + random.random() * 4,
        #     "pressure_trend": random.random() * len(pressure_tendency),
        #     "past_weather_code": random_weather(),
        #     "past_precipitations": (random.random() * 2, random.random() * 5),
        #     "forecast_precipitations": (random.random() * 2, random.random() * 5),
        #     "vicinity": random.random() > 0.5,
        #     "intensity": random.choice(["light", "moderate", "heavy"]),
        #     "virga": random.random() > 0.5,
        #     "past_hour_not_now": random.random() > 0.5,
        #     "past_hour_and_now": random.random() > 0.5,
        #     "decreased_past_hour_occuring_now": random.random() > 0.5,
        #     "obs_utc": datetime.now(),
        # }
        return station_plot_data

    # iconic weather representation
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
        hours = self.button.get_simulator_variable_value("sim/cockpit2/clock_timer/local_time_hours", default=12)
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

    def select_weather_icon(self, at_random: bool = False):
        # Needs improvement
        # Stolen from https://github.com/flybywiresim/efb
        if at_random:
            return random.choice(list(WEATHER_ICONS.values()))

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


#
# Set up mapping objects for various groups of symbols. The integer values follow from
# the WMO.
#
class CodePointMapping:
    """Map integer values to font code points."""

    def __init__(self, num, font_start, font_jumps=None, char_jumps=None):
        """Initialize the instance.

        Parameters
        ----------
        num : int
            The number of values that will be mapped
        font_start : int
            The first code point in the font to use in the mapping
        font_jumps : list[int, int], optional
            Sequence of code point jumps in the font. These are places where the next
            font code point does not correspond to a new input code. This is usually caused
            by there being multiple symbols for a single code. Defaults to :data:`None`, which
            indicates no jumps.
        char_jumps : list[int, int], optional
            Sequence of code jumps. These are places where the next code value does not
            have a valid code point in the font. This usually comes from place in the WMO
            table where codes have no symbol. Defaults to :data:`None`, which indicates no
            jumps.

        """
        next_font_jump = self._safe_pop(font_jumps)
        next_char_jump = self._safe_pop(char_jumps)
        font_point = font_start
        self.chrs = []
        code = 0
        while code < num:
            if next_char_jump and code >= next_char_jump[0]:
                jump_len = next_char_jump[1]
                code += jump_len
                self.chrs.extend([""] * jump_len)
                next_char_jump = self._safe_pop(char_jumps)
            else:
                self.chrs.append(chr(font_point))
                if next_font_jump and code >= next_font_jump[0]:
                    font_point += next_font_jump[1]
                    next_font_jump = self._safe_pop(font_jumps)
                code += 1
                font_point += 1

    @staticmethod
    def _safe_pop(lst):
        """Safely pop from a list.

        Returns None if list empty.

        """
        return lst.pop(0) if lst else None

    def __call__(self, code):
        """Return the Unicode code point corresponding to `code`.

        If code >= 1000, then an alternate code point is returned, with the thousands
        digit indicating which alternate.
        """
        if code < 1000:
            return self.chrs[code]
        else:
            alt = code // 1000
            code %= 1000
            return self.alt_char(code, alt)

    def __len__(self):
        """Return the number of codes supported by this mapping."""
        return len(self.chrs)

    def alt_char(self, code, alt):
        """Get one of the alternate code points for a given value.

        In the WMO tables, some code have multiple symbols. This allows getting that
        symbol rather than main one.

        Parameters
        ----------
        code : int
            The code for looking up the font code point
        alt : int
            The number of the alternate symbol

        Returns
        -------
        int
            The appropriate code point in the font

        """
        return chr(ord(self(code)) + alt) if len(self(code)) > 0 else None

    #####################################################################
    # This dictionary is for mapping METAR present weather text codes
    # to WMO codes for plotting wx symbols along with the station plots.
    # See Attachment IV of WMO No.306 for more information:
    # https://library.wmo.int/index.php?lvl=notice_display&id=13617
    # For unknown precipitation (UP), with thunderstorm this is mapped to 17, otherwise
    # it is mapped to 100 + automated station code

    wx_code_map = {
        "": 0,
        "M": 0,
        "TSNO": 0,
        "VA": 4,
        "FU": 4,
        "HZ": 5,
        "DU": 6,
        "BLDU": 1007,
        "SA": 1007,
        "BLSA": 1007,
        "VCBLSA": 1007,
        "VCBLDU": 1007,
        "BLPY": 1007,
        "PO": 8,
        "VCPO": 8,
        "VCDS": 9,
        "VCSS": 9,
        "BR": 10,
        "BCBR": 10,
        "BC": 11,
        "MIFG": 12,
        "VCTS": 13,
        "VIRGA": 14,
        "VCSH": 16,
        "TS": 17,
        "THDR": 17,
        "VCTSHZ": 17,
        "TSFZFG": 17,
        "TSBR": 17,
        "TSDZ": 17,
        "VCTSUP": 17,
        "-TSUP": 17,
        "TSUP": 17,
        "+TSUP": 17,
        "SQ": 18,
        "FC": 19,
        "+FC": 19,
        "DS": 31,
        "SS": 31,
        "DRSA": 31,
        "DRDU": 31,
        "+DS": 34,
        "+SS": 34,
        "DRSN": 36,
        "+DRSN": 37,
        "-BLSN": 38,
        "BLSN": 38,
        "+BLSN": 39,
        "VCBLSN": 38,
        "VCFG": 40,
        "BCFG": 41,
        "PRFG": 44,
        "FG": 45,
        "FZFG": 49,
        "-VCTSDZ": 51,
        "-DZ": 51,
        "-DZBR": 51,
        "VCTSDZ": 53,
        "DZ": 53,
        "+VCTSDZ": 55,
        "+DZ": 55,
        "-FZDZ": 56,
        "-FZDZSN": 56,
        "FZDZ": 57,
        "+FZDZ": 57,
        "FZDZSN": 57,
        "-DZRA": 58,
        "DZRA": 59,
        "+DZRA": 59,
        "-RA": 61,
        "-RABR": 61,
        "RA": 63,
        "RABR": 63,
        "RAFG": 63,
        "VCRA": 63,
        "+RA": 65,
        "-FZRA": 66,
        "-FZRASN": 66,
        "-FZRABR": 66,
        "-FZRAPL": 66,
        "-FZRASNPL": 66,
        "TSFZRAPL": 67,
        "-TSFZRA": 67,
        "FZRA": 67,
        "+FZRA": 67,
        "FZRASN": 67,
        "TSFZRA": 67,
        "-DZSN": 68,
        "-RASN": 68,
        "-SNRA": 68,
        "-SNDZ": 68,
        "RASN": 69,
        "+RASN": 69,
        "SNRA": 69,
        "DZSN": 69,
        "SNDZ": 69,
        "+DZSN": 69,
        "+SNDZ": 69,
        "-SN": 71,
        "-SNBR": 71,
        "SN": 73,
        "+SN": 75,
        "-SNSG": 77,
        "SG": 77,
        "-SG": 77,
        "IC": 78,
        "-FZDZPL": 79,
        "-FZDZPLSN": 79,
        "FZDZPL": 79,
        "-FZRAPLSN": 79,
        "FZRAPL": 79,
        "+FZRAPL": 79,
        "-RAPL": 79,
        "-RASNPL": 79,
        "-RAPLSN": 79,
        "+RAPL": 79,
        "RAPL": 79,
        "-SNPL": 79,
        "SNPL": 79,
        "-PL": 79,
        "PL": 79,
        "-PLSN": 79,
        "-PLRA": 79,
        "PLRA": 79,
        "-PLDZ": 79,
        "+PL": 79,
        "PLSN": 79,
        "PLUP": 79,
        "+PLSN": 79,
        "-SH": 80,
        "-SHRA": 80,
        "SH": 81,
        "SHRA": 81,
        "+SH": 81,
        "+SHRA": 81,
        "-SHRASN": 83,
        "-SHSNRA": 83,
        "+SHRABR": 84,
        "SHRASN": 84,
        "+SHRASN": 84,
        "SHSNRA": 84,
        "+SHSNRA": 84,
        "-SHSN": 85,
        "SHSN": 86,
        "+SHSN": 86,
        "-GS": 87,
        "-SHGS": 87,
        "FZRAPLGS": 88,
        "-SNGS": 88,
        "GSPLSN": 88,
        "GSPL": 88,
        "PLGSSN": 88,
        "GS": 88,
        "SHGS": 88,
        "+GS": 88,
        "+SHGS": 88,
        "-GR": 89,
        "-SHGR": 89,
        "-SNGR": 90,
        "GR": 90,
        "SHGR": 90,
        "+GR": 90,
        "+SHGR": 90,
        "-TSRASN": 95,
        "TSRASN": 95,
        "-TSSNRA": 95,
        "TSSNRA": 95,
        "-VCTSRA": 1095,
        "-TSRA": 1095,
        "TSRA": 1095,
        "-TSDZ": 1095,
        "VCTSRA": 1095,
        "TSPL": 2095,
        "-TSSN": 2095,
        "-TSPL": 2095,
        "TSSN": 2095,
        "-VCTSSN": 2095,
        "VCTSSN": 2095,
        "TSPLSN": 2095,
        "TSSNPL": 2095,
        "-TSSNPL": 2095,
        "-TSRAGR": 96,
        "TSRAGS": 96,
        "TSRAGR": 96,
        "TSGS": 96,
        "TSGR": 96,
        "+TSFZRAPL": 97,
        "+VCTSRA": 1097,
        "+TSRA": 1097,
        "+TSFZRA": 1097,
        "+TSSN": 2097,
        "+TSPL": 2097,
        "+TSPLSN": 2097,
        "+VCTSSN": 2097,
        "TSSA": 98,
        "TSDS": 98,
        "TSDU": 98,
        "+TSGS": 99,
        "+TSGR": 99,
        "+TSRAGS": 99,
        "+TSRAGR": 99,
        "IN": 141,
        "-UP": 141,
        "UP": 141,
        "+UP": 142,
        "-FZUP": 147,
        "FZUP": 147,
        "+FZUP": 148,
    }


def wx_code_to_numeric(codes):
    """Determine the numeric weather symbol value from METAR code text."""
    wx_sym_list = []
    for s in codes:
        wxcode = s.split()[0] if " " in s else s
        try:
            wx_sym_list.append(CodePointMapping.wx_code_map[wxcode])
        except KeyError:
            if wxcode[0].startswith(("-", "+")):
                options = [slice(None, 7), slice(None, 5), slice(1, 5), slice(None, 3), slice(1, 3)]
            else:
                options = [slice(None, 6), slice(None, 4), slice(None, 2)]

            for opt in options:
                try:
                    wx_sym_list.append(CodePointMapping.wx_code_map[wxcode[opt]])
                    break
                except KeyError:
                    # That option didn't work--move on.
                    pass
            else:
                wx_sym_list.append(0)

    return wx_sym_list


#: Current weather -- codes 1xx are mapped into the automated station symbols
current_weather = CodePointMapping(
    150, 0xE9A2, [(7, 2), (93, 2), (94, 2), (95, 2), (97, 2), (103, -190)], [(0, 4), (100, 3), (106, 4), (113, 5), (119, 1), (136, 4)]
)

#: Current weather from an automated station
current_weather_auto = CodePointMapping(
    100, 0xE94F, [(92, 2), (95, 2)], [(0, 4), (6, 4), (13, 5), (19, 1), (36, 4), (49, 1), (59, 1), (69, 1), (79, 1), (88, 1), (97, 2)]
)

#: Low clouds
low_clouds = CodePointMapping(10, 0xE933, [(7, 1)], [(0, 1)])

#: Mid-altitude clouds
mid_clouds = CodePointMapping(10, 0xE93D, char_jumps=[(0, 1)])

#: High clouds
high_clouds = CodePointMapping(10, 0xE946, char_jumps=[(0, 1)])

#: Sky cover symbols
sky_cover = CodePointMapping(12, 0xE90A)

#: Pressure tendency
pressure_tendency = CodePointMapping(9, 0xE900)
