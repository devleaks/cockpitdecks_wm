# ###########################
# Representation of a Taf in short textual summary form
#
import logging
from textwrap import wrap
from functools import reduce

# these packages have better summary/description of decoded METAR/TAF
import pytaf

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
        retval = [f"Forecast page {bv % len(forecast)} / {len(forecast)}"] + forecast[bv % len(forecast)]
        return reduce(lambda x, t: x + wrap(t, width=21), retval, [])

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

        if self.needs_update():  # update TAF if necessary
            self.update()

        # Generate image on each call based on button value for TAF page

        return self.make_image_for_icon()
