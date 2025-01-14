# ###########################
# Iconic representation of weather ground station plot
#
from __future__ import annotations
import logging
import random
import re
import math
from datetime import datetime
from pprint import pprint

# these packages have better summary/description of decoded METAR/TAF
import pytaf

from PIL import Image, ImageDraw

from cockpitdecks import ICON_SIZE
from cockpitdecks.resources.color import TRANSPARENT_PNG_COLOR

from .weatherdata import WeatherData


logger = logging.getLogger(__name__)
# logger.setLevel(SPAM_LEVEL)
# logger.setLevel(logging.DEBUG)


class WeatherStationPlot(WeatherData):
    """
    Depends on avwx-engine
    """

    REPRESENTATION_NAME = "weather-station-plot"

    def __init__(self, button: "Button"):

        WeatherData.__init__(self, button=button)

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

    # #############################################
    # Cockpitdecks Representation interface
    #
    def get_image_for_icon(self):
        # See:
        # https://geo.libretexts.org/Bookshelves/Meteorology_and_Climate_Science/Practical_Meteorology_(Stull)/09%3A_Weather_Reports_and_Map_Analysis/9.02%3A_Synoptic_Weather_Maps
        # https://en.wikipedia.org/wiki/Station_model

        if self._busy_updating:
            logger.info(f"..updating in progress..")
            return
        self._busy_updating = True
        logger.debug("updating..")

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
            logger.debug("*" * 30 + s)
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

        def draw_flight_rules():
            vis = station_plot_data["flight_rules"]
            if vis is None:
                return
            text = vis
            pd(f"draw_visibility: {vis}, {text}")
            draw.text(
                cell_center(5, 1),
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
            vis = vis / 1000  # metar in meters, here in km
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
            cloudsidx = int(clouds)
            text = low_clouds.alt_char(code=cloudsidx, alt=0)
            pd(f"draw_low_clouds: {clouds}, {text}")
            if text is None:
                logger.warning(f"low_clouds code {cloudsidx} leads to invalid character")
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

            if speed is None and direction is None:
                logger.warning("no wind data")
                return
            # rounds direction to quarter cardinals N-NE
            if speed is None:
                speed = 0  # no wind
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
                    wind_image = wind_image.rotate(angle=180 - direction)
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
                    wind_image = wind_image.rotate(angle=180 - direction)
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
                    x = S12 + (barlength + 4) * math.sin(math.radians(180 - direction))
                    y = S12 + (barlength + 4) * math.cos(math.radians(180 - direction))
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
        draw_flight_rules()
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
        def to_1690(alt: float) -> str:  # code
            code = 0
            if alt < 3000:
                code = int(alt / 30)
            else:
                code = int(alt / 300) * 10
            return f"{code:03d}"

        def from_1690(code: str) -> int:  # meters
            if len(code) != 3:
                logger.warning(f"code 1690: invalid code {code}")
                return 0
            return 30 * int(code)

        # #########################
        # Information/value collection procedures
        #
        # left:
        def value_of(s):
            return s.value if s is not None else None

        def get_plot_temperature():
            return value_of(self.metar.data.temperature)

        def get_plot_visibility():
            return value_of(self.metar.data.visibility)

        def get_plot_current_weather_code():
            codes = [c.repr for c in self.metar.data.wx_codes]
            codenums = wx_code_to_numeric(codes)
            print(">>>>>>", codes, codenums)
            return codenums[0] if len(codenums) > 0 else None

        def get_plot_dew_point():
            return value_of(self.metar.data.dewpoint)

        def get_plot_sea_surface():
            return None

        # center:
        def get_plot_high_clouds():
            return None

        def get_plot_middle_clouds():
            return None

        def get_plot_total_sky_cover():
            return None

        def get_plot_low_clouds():
            return None

        def get_plot_low_clouds_cover():
            return None

        def get_plot_low_clouds_height():
            return None

        def get_plot_waves():
            return (None, None)

        def get_plot_wind():
            variable = len(self.metar.data.wind_variable_direction) > 1
            logger.warning(f"wind variable, speed {value_of(self.metar.data.wind_speed)}")
            return (
                value_of(self.metar.data.wind_speed),
                value_of(self.metar.data.wind_direction),
                value_of(self.metar.data.wind_gust),
            )

        # right:
        def get_plot_flight_rules():
            return self.metar.data.flight_rules

        def get_plot_pressure():
            return value_of(self.metar.data.altimeter)

        def get_plot_pressure_change():
            return None

        def get_plot_pressure_change_trend():
            return None

        def get_plot_obs_utc():
            return self.metar.data.time.dt

        def get_plot_past_weather_code():
            return None

        def get_plot_precipitation_last_time():
            return (None, None)

        def get_plot_six_hour_precipitation_forewast():
            return (None, None)

        # code modifiers: Intensity, Proximity, or Recency
        def is_vicinity():
            return "VC" in self.metar.raw

        def get_intensity():
            return None

        def is_intermittent():
            return None

        def is_virga():
            return None

        # time aournd
        def is_past_hour_not_now():
            return None

        def is_past_hour_and_now():
            return None

        def is_decreased_past_hour_occuring_now():
            return None

        # #########################
        # Compilation
        #
        if at_random:
            logger.warning("using random weather for station plot display")

            def random_weather():
                weather = [random.choice(list(CodePointMapping.wx_code_map.keys()))]
                codes = wx_code_to_numeric(weather)
                # print(">>>", weather, codes)
                return codes[0] if len(codes) > 0 else None  # random.random() * len(current_weather)

            station_plot_data = {
                "temperature": random.random() * 50 - 15,
                "visibility": random.random() * 120,
                "current_weather_code": random_weather(),
                "dew_point": -5 + random.random() * 10,
                "sea_surface": 10 + random.random() * 10,
                "waves": (random.random() * 5, random.random() * 30),
                "high_clouds": random.random() * len(high_clouds),
                "mid_clouds": random.random() * len(mid_clouds),
                "sky_cover": random.random(),
                "low_clouds": random.random() * len(low_clouds),
                "low_clouds_cover": random.random(),
                "low_clouds_base_m": random.random() * 3000,
                "wind": (
                    random.random() * 120,
                    random.random() * 360 if random.random() > 0.5 else None,
                    random.random() * 80 if random.random() > 0.5 else None,
                ),  # kn?
                "pressure": 975 + random.random() * 60,
                "pressure_change": -2 + random.random() * 4,
                "pressure_trend": random.random() * len(pressure_tendency),
                "past_weather_code": random_weather(),
                "past_precipitations": (random.random() * 2, random.random() * 5),
                "forecast_precipitations": (random.random() * 2, random.random() * 5),
                "vicinity": random.random() > 0.5,
                "intensity": random.choice(["light", "moderate", "heavy"]),
                "virga": random.random() > 0.5,
                "past_hour_not_now": random.random() > 0.5,
                "past_hour_and_now": random.random() > 0.5,
                "decreased_past_hour_occuring_now": random.random() > 0.5,
                "obs_utc": datetime.now(),
            }
        else:
            no = "" if self.has_trend() else "no "
            logger.info(f"METAR: {self.metar.raw}, utc={self.metar.data.time.dt}, has {no}trend")
            pprint(self.metar.data)
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
                "flight_rules": get_plot_flight_rules(),
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

        return station_plot_data


# #############################################
# Clouds
#
CLOUD_BASES = [3000, 6000]  # meters, low=ground-3000, mid=3000-6000, high=6000+
CLOUD_BASE_CODES = ["100", "200"]  # meters, low=-100, mid=100-200, high=200+
CLOUD_TYPES = {
    "CI": "Cirrus",
    "CC": "Cirrocumulus",
    "CS": "Cirrostratus",
    "AC": "Altocumulus",
    "ST": "Stratus",
    "CU": "Cumulus",
    "CB": "Cumulonimbus",
    "AS": "Altostratus",
    "NS": "Nimbostratus",
    "SC": "Stratocumulus",
    "TCU": "Cumulus congestus",
}


# #############################################
# WMO
# Set up mapping objects for various groups of symbols. The integer values follow from the WMO.
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
