# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 19:00:56
# @Last Modified by:   nils
# @Last Modified time: 2016-06-23 16:35:24


from instruments.wetlabs import WETLabs
from time import time, gmtime, strftime  # for debugging only


class BB3(WETLabs):

    def __init__(self, _name, _cfg):
        WETLabs.__init__(self, _name, _cfg)

        # Init parameters
        self.m_varname_header = None
        self.m_lambda = []

        # Load cfg
        if 'varname_header' in _cfg.keys():
            self.m_varname_header = _cfg['varname_header']
        else:
            print(_name + ': Missing varname_header')
        if 'lambda' in _cfg.keys():
            self.m_lambda = _cfg['lambda']
        else:
            print(_name + ': Missing lambda')
        if 'units' in _cfg.keys():
            units = _cfg['units']
        else:
            print(_name + ': Missing units')
            units = 'Unknown'

        # Init cache in case log starts before instrument is connected
        for l in self.m_lambda:
            l_str = str(l)
            self.m_cache[self.m_varname_header + l_str] = None
            self.m_units[self.m_varname_header + l_str] = units
            self.m_varnames.append(self.m_varname_header + l_str)

    def UpdateCache(self):
        # readline wait for \EOT or timeout and
        data = self.m_serial.readline()
        if data:
            # data is a byte array
            data = data.rsplit(b'\t', 7)
            if len(data) == 8:
                for i in range(1, 7, 2):
                    self.m_cache[self.m_varname_header +
                                 data[i].decode("UTF-8")] = int(data[i + 1])
                self.m_n += 1
            else:
                # Incomplete data transmission
                self.CommunicationError('Incomplete data transmission.\n' +
                                        'This might happen on few first ' +
                                        'bytes received.\nIf it keeps going ' +
                                        'try disconnecting and reconnecting ' +
                                        'the instrument.')
        else:
            # No data
            self.CommunicationError('No data after updating cache.\n' +
                                    'Suggestions:\n' +
                                    '\t- Serial cable might be unplug.\n' +
                                    '\t- Sensor power is off.\n')
