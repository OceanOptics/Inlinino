# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 16:22:19
# @Last Modified by:   nils
# @Last Modified time: 2016-06-20 15:30:32

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
from time import sleep, time

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
        start_time = time()
        while(self.m_active):
            try:
                self.UpdateCache()
                self.m_n += 1
                sleep(self.m_serial.timeout - (time() - start_time) %
                      self.m_serial.timeout)
            except:
                print(self.m_name +
                      ': Unexpected error while updating cache.\n'
                      'Serial adaptor might be unplug.')
                try:
                    self.EmptyCache()
                    self.NoResponse()
                except:
                    print(self.m_name +
                          ': Unexpected error while emptying cache')

    def UpdateCache(self):
        # Update cache
        #   To be implemented by subclass
        pass

    def NoResponse(self, _msg=None):
        # Set meassage
        if _msg is None:
            msg = _msg
        else:
            msg = 'No data after updating cache.\n' + \
                'Suggestions:\n' + \
                '\t- Serial cable might be unplug.\n' + \
                '\t- Sensor power is off.\n'

        # Set cache to None
        for key in self.m_cache.keys():
            self.m_cache[key] = None

        # Error message if necessary
        self.m_nNoResponse += 1
        if (self.m_nNoResponse >= self.m_maxNoResponse and
                self.m_nNoResponse % 60 == self.m_maxNoResponse):
            print('%s did not respond %d times\n%s' % (self.m_name,
                                                       self.m_nNoResponse,
                                                       msg))


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
