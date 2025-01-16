# ###########################
# Representation of a Taf in short textual summary form
#
import logging
from textwrap import wrap
from functools import reduce

# these packages have better summary/description of decoded METAR/TAF
import pytaf

from PIL import Image, ImageDraw

from cockpitdecks import ICON_SIZE
from cockpitdecks.resources.iconfonts import (
    WEATHER_ICONS,
    WEATHER_ICON_FONT,
    DEFAULT_WEATHER_ICON,
)
from cockpitdecks.resources.color import light_off, TRANSPARENT_PNG_COLOR

from .weathermetar import WeatherMetarIcon

logger = logging.getLogger(__name__)
# logger.setLevel(SPAM_LEVEL)
# logger.setLevel(logging.DEBUG)


class WeatherTafIcon(WeatherMetarIcon):
    """
    Depends on avwx-engine
    """

    REPRESENTATION_NAME = "weather-taf"

    def __init__(self, button: "Button"):

        WeatherMetarIcon.__init__(self, button=button)

    def get_lines(self) -> list | None:
        # We collect all forecasts, and display them in turn
        if not hasattr(self.taf, "summary"):
            logger.warning(f"TAF has no summary")
            return None

        # return reduce(lambda x, t: x + wrap(t, width=21), self.taf.summary, [])
        bv = self.button.value
        bv = 0 if bv is None else int(bv)
        taf_text = pytaf.Decoder(pytaf.TAF(self.taf.raw)).decode_taf()
        # Split TAF in blocks of forecasts
        forecast = []
        prevision = []
        for line in taf_text.split("\n"):
            if len(line.strip()) > 0:
                prevision.append(line)
            else:
                forecast.append(prevision)
                prevision = []
        return [f"Forecast page {bv % len(forecast)} / {len(forecast)}"] + forecast[bv % len(forecast)]

    def get_image_for_icon(self):
        """
        Helper function to get button image and overlay label on top of it.
        Label may be updated at each activation since it can contain datarefs.
        Also add a little marker on placeholder/invalid buttons that will do nothing.
        """
        print("yup")
        if self._busy_updating:
            logger.info("..updating in progress..")
            return
        self._busy_updating = True
        logger.debug("updating..")

        # if not self.update() and self._cache is not None:
        #     print("yup no update")
        #     logger.debug("..not updated, using cache")
        #     self._busy_updating = False
        #     return self._cache
        if self.needs_update():
            self.update()

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

        # Weather Forecast Data
        # This will do for now
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
