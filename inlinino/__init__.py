import logging
from logging.handlers import RotatingFileHandler
from time import strftime, gmtime
import sys
import os
import traceback

import numpy as np


__version__ = '2.9.8'

# Setup Logger
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('PyQt5').setLevel(logging.WARNING)
root_logger = logging.getLogger()   # Get root logger


# Catch errors in log
def except_hook(exc_type, exc_value, exc_tb):
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    root_logger.error(tb)


sys.excepthook = except_hook


# Setup Path
if hasattr(sys, 'frozen') and hasattr(sys, '_MEIPASS'):
    root_logger.debug('Running in bundled mode')
    package_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
    os.chdir(package_dir)
else:
    root_logger.debug('Running from source')
    package_dir = os.path.dirname(__file__)
PATH_TO_RESOURCES = os.path.join(package_dir, 'resources')


# Logging in file
path_to_log = os.path.join(package_dir, 'logs')
if not os.path.isdir(path_to_log):
    root_logger.debug('Create log directory: %s' % path_to_log)
    os.mkdir(path_to_log)
log_filename = os.path.join(path_to_log, 'inlinino_' + strftime('%Y%m%d_%H%M%S', gmtime()) + '.log')
ch_file = RotatingFileHandler(log_filename, maxBytes=1048576 * 5, backupCount=9)
formater_file = logging.Formatter("%(asctime)s %(levelname)-8.8s [%(name)s]  %(message)s")
ch_file.setFormatter(formater_file)
root_logger.addHandler(ch_file)


class RingBuffer:
    # Ring buffer based on numpy.roll for np.array
    # Same concept as FIFO except that the size of the numpy array does not vary
    def __init__(self, _length, _dtype=None):
        # initialize buffer with NaN values
        # length correspond to the size of the buffer
        if _dtype is None:
            self.data = np.empty(_length)  # np.dtype = float64
            self.data[:] = np.NAN
        else:
            # type needs to be compatible with np.NaN
            self.data = np.empty(_length, dtype=_dtype)
            self.data[:] = None

    def extend(self, _x):
        # Add np.array at the end of the buffer
        x = np.array(_x, copy=False)  # dtype=None
        step = x.size
        self.data = np.roll(self.data, -step)
        self.data[-step:] = x

    def get(self, _n=1):
        # return the most recent n element(s) in buffer
        return self.data[-1 * _n:]

    def getleft(self, _n=1):
        # return the oldest n element(s) in buffer
        return self.data[0:_n]

    def __str__(self):
        return str(self.data)


# Set Constant(s)
COLOR_SET = ['#1f77b4',  # muted blue
             '#2ca02c',  # cooked asparagus green
             '#ff7f0e',  # safety orange
             '#d62728',  # brick red
             '#9467bd',  # muted purple
             '#8c564b',  # chestnut brown
             '#e377c2',  # raspberry yogurt pink
             '#7f7f7f',  # middle gray
             '#bcbd22',  # curry yellow-green
             '#17becf']  # blue-teal
