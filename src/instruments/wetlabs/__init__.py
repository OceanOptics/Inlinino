# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 16:22:19
# @Last Modified by:   nils
# @Last Modified time: 2016-06-24 11:47:44

# To check sensor is working correctly:
# On OSX:
#   screen /dev/tty.usbserial-FTZ267A6A 19200
#   close session with ctrl-A ctrl-\
# On Windows:
#   Use TeraTerm baudrate 19200


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
        self.m_varname_header = None
        self.m_lambda = []

        # Initialize serial communication
        self.m_serial = Serial()
        self.m_serial.baudrate = 19200
        self.m_serial.bytesize = 8
        self.m_serial.parity = 'N'  # None
        self.m_serial.stopbits = 1
        self.m_serial.timeout = 1   # 1 Hz

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

    def RunUpdateCache(self):
        while(self.m_active):
            try:
                self.UpdateCache()
            except Exception as e:
                print(self.m_name +
                      ': Unexpected error while updating cache.\n' +
                      'Suggestions:\n' +
                      '\t-Serial adaptor might be unplug.')
                try:
                    self.EmptyCache()
                    self.CommunicationError()
                except:
                    print(self.m_name +
                          ': Unexpected error while emptying cache')
                print(e)

    def UpdateCache(self):
        # Update cache
        #   To be implemented by subclass
        pass

    def CommunicationError(self, _msg=''):
        # Set cache to None
        for key in self.m_cache.keys():
            self.m_cache[key] = None

        # Error message if necessary
        self.m_nNoResponse += 1
        if (self.m_nNoResponse >= self.m_maxNoResponse and
                self.m_nNoResponse % 60 == self.m_maxNoResponse):
            print('%s did not respond %d times\n%s' % (self.m_name,
                                                       self.m_nNoResponse,
                                                       _msg))


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
