# ###########################
# Representation of a Metar in short textual summary form
#
from __future__ import annotations
import logging
from datetime import datetime

from avwx import Station, Metar, Taf

from PIL import Image, ImageDraw

from cockpitdecks import ICON_SIZE
from cockpitdecks.resources.iconfonts import (
    WEATHER_ICONS,
    WEATHER_ICON_FONT,
    DEFAULT_WEATHER_ICON,
)
from cockpitdecks.resources.color import light_off, TRANSPARENT_PNG_COLOR
from cockpitdecks.resources.geo import distance
from cockpitdecks.simulator import SimulatorVariable

from .weatherdata import WeatherData

logger = logging.getLogger(__name__)
# logger.setLevel(SPAM_LEVEL)
# logger.setLevel(logging.DEBUG)


class WeatherMetarIcon(WeatherData):
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
        WeatherData.__init__(self, button=button)

    # #############################################
    # Cockpitdecks Representation interface
    #
    def get_variables(self) -> set:
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
        self.button._config["label"] = icao

        # invalidate previous values
        self.metar = None
        self._cache = None
        self.update(force=True)

    def get_image_for_icon(self):
        """
        Helper function to get button image and overlay label on top of it.
        Label may be updated at each activation since it can contain datarefs.
        Also add a little marker on placeholder/invalid buttons that will do nothing.
        """
        if self._busy_updating:
            logger.info("..updating in progress..")
            return
        self._busy_updating = True
        logger.debug("updating..")

        if not self.update() and self._cache is not None:
            logger.debug("..not updated, using cache")
            self._busy_updating = False
            return self._cache

        return self.make_image_for_icon()

    def get_lines(self) -> list | None:
        lines = None
        try:
            if self.has_metar("summary"):
                lines = self.metar.summary.split(",")  # ~ 6-7 short lines
        except:
            lines = None
            logger.warning(f"Metar has no summary")
        return lines

    def make_image_for_icon(self):
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
        lines = self.get_lines()

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
