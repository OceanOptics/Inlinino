import json
import logging
import os
import sys
import uuid


from inlinino import package_dir


PATH_TO_CFG_FILE = os.path.join(package_dir, 'inlinino_cfg.json')


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
    def __init__(self):
        self.__logger = logging.getLogger('CFG')
        self.instruments, self.interfaces = dict(), dict()
        self.read()

    def read(self):
        with open(PATH_TO_CFG_FILE) as file:
            self.__logger.debug('Reading configuration.')
            cfg = json.load(file, object_hook=as_bytes)
        if 'instruments' not in cfg.keys():
            self.__logger.critical('Unable to load instruments from configuration file.')
            sys.exit(-1)
        if isinstance(cfg['instruments'], list):
            # Append UUID to Legacy format
            d = dict()
            for i in cfg['instruments']:
                d[str(uuid.uuid1())] = i
            self.instruments = d
        else:
            self.instruments = cfg['instruments']
        if 'interfaces' in cfg.keys():
            self.interfaces = cfg['interfaces']

    def write(self):
        self.__logger.info('Writing configuration.')
        cfg = {'instruments': self.instruments, 'interfaces': self.interfaces}
        with open(PATH_TO_CFG_FILE, 'w') as file:
            json.dump(cfg, file, cls=BytesEncoder)


CFG = Cfg()
