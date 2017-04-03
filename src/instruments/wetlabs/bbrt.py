# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2017-04-03 13:38:39
# @Last Modified by:   nils
# @Last Modified time: 2017-04-03 14:08:23

# Column header in order:
#   %m/%d/%y
#   %H:%M:%S
#   temperature (count)
#   backscattering (count)
#   checksum

from instruments.wetlabs import WETLabs
# from time import time, gmtime, strftime  # for debugging only


class BBRT(WETLabs):

    def __init__(self, _name, _cfg):
        WETLabs.__init__(self, _name, _cfg)

    def UpdateCache(self):
        # readline wait for \EOT or timeout and
        data = self.m_serial.readline()
        if data:
            # data is a byte array
            data = data.rsplit(b'\t', 2)
            if len(data) == 3:
                self.m_cache[self.m_varnames[0]] = int(data[1])
                self.m_cacheIsNew[self.m_varnames[0]] = True
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
