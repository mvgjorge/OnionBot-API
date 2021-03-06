from threading import Thread, Event
from queue import Queue, Empty

import math
from statistics import mean
import time
import board
import busio
from PIL import Image
from collections import deque

import adafruit_mlx90640
import logging

logger = logging.getLogger(__name__)


CHESSBOARD_MAX_THRESHOLD = 300
CHESSBOARD_MIN_THRESHOLD = 5

TEMPERATURE_MULTIPLIER = 1.35
TEMPERATURE_OFFSET = -6


INTERPOLATE = 10

MINTEMP = 20.0  # -40 #low range of the sensor (this will be black on the screen)
MAXTEMP = 200.0  # previous 50 #max 300 #high range of the sensor (this will be white on the screen)
SCALE = 25


# the list of colors we can choose from
heatmap = (
    (0.0, (0, 0, 0)),
    (0.20, (0, 0, 0.5)),
    (0.40, (0, 0.5, 0)),
    (0.60, (0.5, 0, 0)),
    (0.80, (0.75, 0.75, 0)),
    (0.90, (1.0, 0.75, 0)),
    (1.00, (1.0, 1.0, 1.0)),
)

# how many color values we can have
COLORDEPTH = 1000

colormap = [0] * COLORDEPTH


class ThermalCamera(object):
    """Save image to file"""

    def __init__(self, i2c=None, visualise_on=False):

        self.quit_event = Event()

        logger.info("Initialising thermal camera...")

        if i2c is None:
            i2c = busio.I2C(board.SCL, board.SDA)

        mlx = adafruit_mlx90640.MLX90640(i2c)
        mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_32_HZ

        self.mlx = mlx

        self.file_queue = Queue(1)

        self.temperature = 0
        self.thermal_history = deque([0] * 120)

        self.data = {
            "temperature": None,
            "thermal_history": None,
        }

    def _constrain(self, val, min_val, max_val):
        return min(max_val, max(min_val, val))

    def _map_value(self, x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def _gaussian(self, x, a, b, c, d=0):
        return a * math.exp(-((x - b) ** 2) / (2 * c ** 2)) + d

    def _gradient(self, x, width, cmap, spread=1):
        width = float(width)
        r = sum(
            [
                self._gaussian(x, p[1][0], p[0] * width, width / (spread * len(cmap)))
                for p in cmap
            ]
        )
        g = sum(
            [
                self._gaussian(x, p[1][1], p[0] * width, width / (spread * len(cmap)))
                for p in cmap
            ]
        )
        b = sum(
            [
                self._gaussian(x, p[1][2], p[0] * width, width / (spread * len(cmap)))
                for p in cmap
            ]
        )
        r = int(self._constrain(r * 255, 0, 255))
        g = int(self._constrain(g * 255, 0, 255))
        b = int(self._constrain(b * 255, 0, 255))
        return r, g, b

    def _worker(self):
        def _value(frame):

            logger.debug("Proccessing numerical data")

            f = frame
            center_square = [
                f[72],
                f[73],
                f[74],
                f[75],
                f[88],
                f[89],
                f[90],
                f[91],
                f[104],
                f[105],
                f[106],
                f[107],
                f[120],
                f[121],
                f[122],
                f[123],
            ]

            temperature = mean(center_square)
            temperature = (temperature * TEMPERATURE_MULTIPLIER) + TEMPERATURE_OFFSET
            temperature = "{:.1f}".format(temperature)

            self.temperature = temperature

            thermal_history = self.thermal_history
            thermal_history.append(temperature)
            thermal_history.popleft()
            self.thermal_history = thermal_history

            return thermal_history

        def _image(frame, file_path):

            logger.debug("Proccessing image data")

            for i in range(COLORDEPTH):
                colormap[i] = self._gradient(i, COLORDEPTH, heatmap)

            pixels = [0] * 768
            for i, pixel in enumerate(frame):
                coloridx = self._map_value(pixel, MINTEMP, MAXTEMP, 0, COLORDEPTH - 1)
                coloridx = int(self._constrain(coloridx, 0, COLORDEPTH - 1))
                pixels[i] = colormap[coloridx]

            img = Image.new("RGB", (32, 24))
            img.putdata(pixels)
            img = img.resize((24 * INTERPOLATE, 24 * INTERPOLATE), Image.BICUBIC)

            img = img.transpose(method=Image.ROTATE_90)
            img = img.transpose(method=Image.FLIP_LEFT_RIGHT)
            img.save(file_path)

        while True:

            try:  # Timeout raises queue.Empty
                file_path = self.file_queue.get(block=True, timeout=0.1)

                logger.debug("Capturing frame")
                frame = [0] * 768
                stamp = time.monotonic()
                while True:
                    try:
                        self.mlx.getFrame(frame)
                    except ValueError:  # Handle ValueError in module
                        logger.debug("Frame capture error, retrying [ValueError]")
                        time.sleep(0.1)
                        continue
                    except RuntimeError:  # Handle RuntimeError in module
                        logger.debug("Frame capture error, retrying [RuntimeError]")
                        time.sleep(0.1)
                        continue
                    except OSError:  # Handle RuntimeError in module
                        logger.info("Frame capture error, retrying [OSError]")
                        time.sleep(0.1)
                        continue

                    if 0 in frame:  # Handle chessboard error zeros
                        logger.debug("Frame capture error, retrying [Zero Error]")
                        time.sleep(0.1)
                        continue

                    if max(frame) > CHESSBOARD_MAX_THRESHOLD:
                        logger.debug(
                            "Frame capture error, retrying [Max Temp Error: %0.2f ]"
                            % (max(frame))
                        )
                        time.sleep(0.1)
                        continue
                    elif min(frame) < CHESSBOARD_MIN_THRESHOLD:
                        logger.debug(
                            "Frame capture error, retrying [MIN Temp Error: %0.2f ]"
                            % (min(frame))
                        )
                        time.sleep(0.1)
                        continue

                    break

                logger.debug("Read 2 frames in %0.3f s" % (time.monotonic() - stamp))

                # Call numerical and graphical functions
                _value(frame)
                _image(frame, file_path)

                self.file_queue.task_done()

            except Empty:
                if self.quit_event.is_set():
                    logger.debug("Quitting thermal camera thread...")
                    break

    def get_temperature(self):
        temperature = self.temperature
        logger.debug("self.temperature is %s " % (temperature))

        return temperature

    def get_thermal_history(self):
        thermal_history = list(self.thermal_history)
        logger.debug("self.thermal_history is %s " % (thermal_history))

        return thermal_history

    def start(self, file_path):
        logger.debug("Calling start")
        self.file_queue.put(file_path, block=True)

    def join(self):
        logger.debug("Calling join")
        self.file_queue.join()

        self.data = {
            "temperature": self.get_temperature(),
            "thermal_history": self.get_thermal_history(),
        }

    def launch(self):
        logger.debug("Initialising worker")
        self.thread = Thread(target=self._worker, daemon=True)
        self.thread.start()

    def quit(self):
        self.quit_event.set()
        self.thread.join()
