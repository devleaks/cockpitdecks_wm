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
from .weathericon import WeatherIcon

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
        self.weather_icon = None
        self.weather_icon_factory = WeatherIcon()  # decorating weather icon image
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
            if self.weather_icon_factory is not None:
                self.weather_icon = self.weather_icon_factory.select_weather_icon(metar=self.metar, station=self.station)
            logger.debug(f"Metar updated for {self.station.icao}, icon={self.weather_icon}, updated={updated}")
            self.inc("real update")

        return updated
