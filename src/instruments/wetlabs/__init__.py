# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 16:22:19
# @Last Modified by:   nils
# @Last Modified time: 2016-05-25 02:32:15

# To check sensor is working correctly:
# On OSX:
#   screen /dev/tty.usbserial-FTZ267A6A 19200
#   close session with ctrl-A ctrl-\
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

from serial import Serial
from threading import Thread
from time import sleep

from instruments import Instrument


class WETLabs(Instrument):
    '''
    Interface to serial WET Labs sensors
    '''

    # Parameters
    m_thread = None
    m_serial = None
    # Non Responsive Counter
    m_nNonResponse = 0
    m_maxNonResponse = 10

    def __init__(self, _name, _cfg):
        Instrument.__init__(self, _name)

        # Do specific configuration needed to date

        # Initialize serial communication
        self.m_serial = Serial()
        self.m_serial.baudrate = 19200
        self.m_serial.bytesize = 8
        self.m_serial.parity = 'N'  # None
        self.m_serial.stopbits = 1
        self.m_serial.timeout = 1   # 1 Hz

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
            # Create thread to update cache
            self.m_thread = Thread(target=self.RunCacheUpdate, args=())
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
                self.m_thread.join(self.m_timeout * 1.1)
            else:
                print(self.m_name + 'thread already close.')
        # Close serial connection
        if self.m_serial.isOpen():
            self.m_serial.close()
        else:
            print(self.m_name + 'serial communication already close.')
        # Empty cache
        self.EmptyCache()

    def RunUpdateCache(self):
        while(self.m_active):
            sleep(self.m_serial.timeout)
            try:
                self.UpdateCache()
            except:
                print('Unexpected error while updating cache.\n'
                      'Serial adaptor might be unplug.')
                try:
                    for var in self.m_cache.keys():
                        self.m_cache[var] = None
                except:
                    print('Unexpected error while emptying cache')

    def UpdateCache(self):
        # Update cache
        #   To be implemented by subclass
        pass

    def NoResponse(self, _msg):
        # Set cache to None
        for key in self.m_cache.keys():
            self.m_cache[key] = None
        # Error message if necessary
        self.m_nNonResponse += 1
        if (self.m_nNonResponse >= self.m_maxNonResponse and
                self.m_nNonResponse % 2400 == self.m_maxNonResponse):
            print('%s did not respond %d times\n%s' % (self.m_name,
                                                       self.m_nNonResponse,
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
