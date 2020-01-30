# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 16:22:19
# @Last Modified by:   nils
# @Last Modified time: 2017-01-16 09:34:41

# To check sensor is working correctly:
# On OSX:
#   screen /dev/tty.usbserial-FTZ267A6A 19200
#   close session with ctrl-A ctrl-\
# On Windows:
#   Use TeraTerm baudrate 19200

from time import sleep
from serial import Serial
from threading import Thread
from instruments import Instrument


class WETLabs(Instrument):
    '''
    Interface to serial WET Labs sensors
    '''

    def __init__(self, _name, _cfg):
        Instrument.__init__(self, _name)

        # No Responsive Counter
        self.m_maxNoResponse = 10

        # Do specific configuration
        self.m_connect_need_port = True
        self.m_lambda = []

        # Initialize serial communication
        self.m_serial = Serial()
        self.m_serial.baudrate = 19200
        self.m_serial.bytesize = 8
        self.m_serial.parity = 'N'  # None
        self.m_serial.stopbits = 1
        self.m_serial.timeout = 2   # Instrument run at 1 Hz so let him a chance to speak (> 1)

        # Load cfg
        if 'lambda' in _cfg.keys():
            self.m_lambda = _cfg['lambda']
        else:
            print(_name + ': Missing lambda')
            exit()
        if 'varname_header' in _cfg.keys():
            if isinstance(_cfg['varname_header'], str):
                varname_header = [_cfg['varname_header']
                                  for i in range(len(self.m_lambda))]
            elif isinstance(_cfg['varname_header'], list):
                varname_header = _cfg['varname_header']
            else:
                print(_name + ':Incompatible instance type for varname_header')
                exit()
        else:
            if __debug__:
                print(_name + ': Missing varname_header')
            varname_header = ['' for i in range(len(self.m_lambda))]
        if 'units' in _cfg.keys():
            if isinstance(_cfg['units'], str):
                units = [_cfg['units'] for i in range(len(self.m_lambda))]
            elif isinstance(_cfg['units'], list):
                units = _cfg['units']
            else:
                print(_name + ': Incompatible instance type for units')
                exit()
        else:
            print(_name + ': Missing units')
            units = ['Unknown' for i in range(len(self.m_lambda))]

        # Check size of arrays
        if len(self.m_lambda) != len(units) or \
                len(self.m_lambda) != len(varname_header):
            print(_name + ': arrays units, varname_header and lambda ' +
                  'have different size')
            print(self.m_lambda, units, varname_header)
            exit()

        # Init cache in case log starts before instrument is connected
        for l in self.m_lambda:
            varname = varname_header.pop(0) + str(l)
            self.m_cache[varname] = None
            self.m_cacheIsNew[varname] = False
            self.m_units[varname] = units.pop(0)
            self.m_varnames.append(varname)

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
            # sleep(self.m_serial.timeout)    # Wait for instrument to start
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
                # self.m_thread.join(self.m_serial.timeout * 1.1)
                self.m_thread.join(self.m_serial.timeout)
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


# Simple example logging the data
if __name__ == '__main__':
    BB3_349 = WETLabs()

    # Connect with port
    BB3_349.Connect('/dev/tty.usbserial-FTZ267A6A')
    sleep(BB3_349.m_serial.timeout)

    if BB3_349.m_active:
        # UpdateCache 10 times
        for i in range(1, 10):
            sleep(BB3_349.m_serial.timeout)
            print(BB3_349.ReadCache())

    # Close connection
    BB3_349.Close()
