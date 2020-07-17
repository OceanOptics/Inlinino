# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-14 16:55:33
# @Last Modified by:   nils
# @Last Modified time: 2016-07-05 16:28:37
import numpy as np
import logging
import json
import sys

__version__ = '2.1'


logging.basicConfig(level=logging.DEBUG)
# TODO Add logging to a file


class BytesEncoder(json.JSONEncoder):
    ENCODING = 'ascii'

    def default(self, obj):
        if isinstance(obj, bytes):
            return {'__bytes__': self.ENCODING, 'content': obj.decode(self.ENCODING)}
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


def as_bytes(dct):
    if '__bytes__' in dct:
        return bytes(dct['content'], dct['__bytes__'])
    return dct


class Cfg:
    FILENAME = 'inlinino_cfg.json'
    KEYS_NOT_SAVED = ['log_prefix']

    def __init__(self):
        self.__logger = logging.getLogger('cfg')
        with open(self.FILENAME) as file:
            logging
            cfg = json.load(file, object_hook=as_bytes)
        if 'instruments' not in cfg.keys():
            self.__logger.critical('Unable to load instruments from configuration file.')
            sys.exit(-1)
        self.instruments = cfg['instruments']

    def write(self):
        self.__logger.info('Writing configuration.')
        cfg = {'instruments': []}
        # Remove keys not saved
        for i in self.instruments:
            foo = i.copy()
            for k in self.KEYS_NOT_SAVED:
                if k in foo.keys():
                    del foo[k]
            cfg['instruments'].append(foo)
        with open(self.FILENAME, 'w') as file:
            json.dump(cfg, file, cls=BytesEncoder)


CFG = Cfg()


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
