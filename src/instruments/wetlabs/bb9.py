# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 19:00:56
# @Last Modified by:   nils
# @Last Modified time: 2016-06-23 17:30:12


from instruments.wetlabs import WETLabs
from threading import Thread
from time import sleep


class BB9(WETLabs):

    def __init__(self, _name, _cfg):
        WETLabs.__init__(self, _name, _cfg)

    def Connect(self, _port=None):
        if _port is None:
            print(self.m_name + ' need a port to establish connection.')
            return None

        try:
            self.m_serial.port = _port
            self.m_serial.open()
        except:
            print('%s did not respond' % (self.m_name))
            return None

        if self.m_serial.isOpen():
            # Skip first data
            self.m_serial.readline()        # First empty line
            sleep(self.m_serial.timeout)    # Wait for instrument to start
            self.m_serial.readline()        # Persistor CF1 SN:51959  BIOS:...
            self.m_serial.readline()        # \r\n
            self.m_serial.readline()        # BB9 S/N 279 v1.03 Compiled on ...
            self.m_serial.readline()        # \r\n
            # Create thread to update cache
            self.m_thread = Thread(target=self.RunUpdateCache, args=())
            self.m_thread.daemon = True
            self.m_active = True
            self.m_thread.start()
            return True
        else:
            return None

    def UpdateCache(self):
        # readline wait for \EOT or timeout and
        data = self.m_serial.readline()
        if data:
            # data is a byte array
            data = data.rsplit(b'\t', 19)
            if len(data) == 20:
                for i in range(1, 19, 2):
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
