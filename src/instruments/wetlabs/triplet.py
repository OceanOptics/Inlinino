# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 19:00:56
# @Last Modified by:   nils
# @Last Modified time: 2016-07-05 16:13:21
#
# Column header in order:
#   %m/%d/%y
#   %H:%M:%S
#   wv(nm)
#   count
#   wv(nm)
#   count
#   wv(nm)
#   count
#   checksum (528) ???

from instruments.wetlabs import WETLabs
# from time import time, gmtime, strftime  # for debugging only


class Triplet(WETLabs):

    def __init__(self, _name, _cfg):
        WETLabs.__init__(self, _name, _cfg)

    def UpdateCache(self):
        # readline wait for \EOT or timeout and
        data = self.m_serial.readline()
        if data:
            # data is a byte array
            data = data.rsplit(b'\t', 7)
            if len(data) == 8:
                for i in range(1, 7, 2):
                    varname = self.m_varnames[int((i - 1) / 2)]
                    l = int(data[i])
                    if l in self.m_lambda:
                        self.m_cache[varname] = int(data[i + 1])
                        self.m_cacheIsNew[varname] = True
                    else:
                        # Unknown variable
                        self.CommunicationError('Unknown variable ' + varname +
                                                '.\nThis might happen on few' +
                                                ' first bytes received.\nIf ' +
                                                'it keeps going  this might ' +
                                                'be due to a wrong ' +
                                                'configuration file.')
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
