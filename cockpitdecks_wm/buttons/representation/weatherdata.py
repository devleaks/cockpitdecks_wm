# ###########################
# Base class for representations that fetches METAR and TAF data periodically.
#
import logging
from datetime import datetime, date

# these packages have better METAR/TAF collection and exposure
from avwx import Station, Metar, Taf
from suntime import Sun

# these packages have better summary/description of decoded METAR/TAF
from metar import Metar as MetarDesc
import pytaf

from cockpitdecks.resources.geo import distance
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


class WeatherData(DrawAnimation, SimulatorVariableListener):
    """
    Depends on avwx-engine
    """

    REPRESENTATION_NAME = "weather-data"

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
        WeatherData.MIN_UPDATE = int(refresh_location) * 60

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
            icao = WeatherData.DEFAULT_STATION  # start with default position
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
        raise NotImplemented("weather data base class has no representation")

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
            if diff < WeatherData.MIN_UPDATE:
                logger.debug(f"updated less than {WeatherData.MIN_UPDATE} secs. ago ({diff}), skipping update.. ({self.speed})")
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
                icao = self.weather.get("station", WeatherData.DEFAULT_STATION)
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
            ret = not self._moved and self.station.icao == self.weather.get("station", WeatherData.DEFAULT_STATION)
            logger.debug(
                f"currently at {self.station.icao}, default station {self.weather.get('station', WeatherData.DEFAULT_STATION)}, moved={self._moved}, returns {ret}"
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
        if diff > WeatherData.MIN_UPDATE:
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
                    if diff > WeatherData.MIN_UPDATE:
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

    def select_weather_icon(self, at_random: bool = False):
        return None
