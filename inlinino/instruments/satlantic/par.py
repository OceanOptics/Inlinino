# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-07-05 14:28:07
# @Last Modified by:   nils
# @Last Modified time: 2017-01-15 17:52:39

from instruments.satlantic import Satlantic


class PAR(Satlantic):

    def __init__(self, _name, _cfg):
        Satlantic.__init__(self, _name, _cfg)

    def UpdateCache(self):
        # readline wait for \EOT or timeout
        data = self.m_serial.readline()
        if data:
            # data is a byte array
            # data = data[1:-3].split(b', ', 2) # in case there is " at beginning and end of line
            data = data[:-2].split(b', ', 2)
            print(data)
            if len(data) == 3:
                for i in range(0, 3):
                    varname = self.m_varnames[i]
                    self.m_cache[varname] = float(data[i])
                    self.m_cacheIsNew[varname] = True
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
