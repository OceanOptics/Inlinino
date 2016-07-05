# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 19:00:56
# @Last Modified by:   nils
# @Last Modified time: 2016-07-05 14:38:04

from time import sleep
from serial import Serial
from threading import Thread
from instruments import Instrument


class SBE(Instrument):

    def __init__(self, _name, _cfg):
        Instrument.__init__(self, _name)

        # No Responsive Counter
        self.m_maxNoResponse = 10

        # Do specific configuration
        self.m_connect_need_port = True
        self.m_varnames = None
        self.m_lambda = []

        # Initialize serial communication
        self.m_serial = Serial()
        self.m_serial.baudrate = 19200
        self.m_serial.bytesize = 8
        self.m_serial.parity = 'N'  # None
        self.m_serial.stopbits = 1
        self.m_serial.timeout = 1   # 1 Hz

        # Load cfg
        if 'variables' in _cfg.keys():
            self.m_varnames = _cfg['variables']
        else:
            print(_name + ': Missing varriables')
            exit()
        if 'units' in _cfg.keys():
            units = _cfg['units']
        else:
            print(_name + ': Missing units')
            units = ['Unknown' for i in range(len(self.m_varnames))]

        # Init cache in case log starts before instrument is connected
        for v in self.m_varnames:
            self.m_cache[v] = None
            self.m_cacheIsNew[v] = False
            self.m_units[v] = units.pop(0)

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
            self.m_serial.readline()
            sleep(self.m_serial.timeout)    # Wait for instrument to start
            self.m_serial.readline()
            # Create thread to update cache
            self.m_thread = Thread(target=self.RunUpdateCache, args=())
            self.m_thread.daemon = True
            self.m_active = True
            self.m_thread.start()
            return True
        else:
            return None

    def Close(self):
        # Stop thread updating cache
        if self.m_thread is not None:
            self.m_active = False
            if self.m_thread.isAlive():
                self.m_thread.join(self.m_serial.timeout * 1.1)
            else:
                print(self.m_name + ' thread already close.')
        # Close serial connection
        if self.m_serial.isOpen():
            self.m_serial.close()
        else:
            print(self.m_name + ' serial communication already close.')
        # Empty cache
        self.EmptyCache()

    def UpdateCache(self):
        # Update cache
        #   To be implemented by subclass
        pass
