# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 16:22:19
# @Last Modified by:   nils
# @Last Modified time: 2016-04-21 08:28:04

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

# TODO user buffer of serialpy directly as cache

from __future__ import division

from serial import Serial
from threading import Thread
from time import sleep

from instrumentino.controllers import InstrumentinoController
from instrumentino import cfg
from instrumentino.comp import SysComp, SysVarAnalog


class WETLabs(InstrumentinoController):
    ''' This class implements an interface to serial WET Labs sensors '''
    # Inspired by class arduino from yoelk

    # Instrument name
    m_name = "WET Labs"

    # Non Responsive Counter
    m_nNonResponse = 0
    m_maxNonResponse = 10

    # Cache
    m_countValuesCache = {}
    m_thread = None
    m_serial = None
    m_active = False

    def __init__(self):
        InstrumentinoController.__init__(self, self.m_name)
        self.m_serial = Serial()
        # WET Labs serial communication constants
        self.m_serial.baudrate = 19200
        self.m_serial.bytesize = 8
        self.m_serial.parity = 'N'  # None
        self.m_serial.stopbits = 1
        self.m_serial.timeout = 1   # 1 Hz

    def Connect(self, _port):
        try:
            self.m_serial.port = _port
            self.m_serial.open()
        except:
            cfg.LogFromOtherThread('%s did not respond' % (self.m_name), True)
            return None

        if self.m_serial.isOpen():
            # Set state to active (allow runCacheUpdate to run)
            self.m_active = True
            # Create thread to update cache
            self.m_thread = Thread(target=self.RunCacheUpdate, args=())
            self.m_thread.daemon = True
            self.m_thread.start()
            return True
        else:
            return None

    def Close(self):
        # Stop thread updating cache
        if self.m_thread is not None:
            self.m_active = False
            self.m_thread.join()
        # Close serial connection
        if self.m_serial.isOpen():
            self.m_serial.close()

    def RunCacheUpdate(self):
        while(self.m_active):
            sleep(self.m_serial.timeout)
            try:
                self.CacheUpdate()
            except:
                self.NoResponse('Unexpected error while updating cache.\n'
                                'Serial adaptor might be unplug.')

    def CacheUpdate(self):
        # read all line in buffer
        data = self.m_serial.readlines()
        if data:
            # keep only most recent data
            data = data[-1]
            # There is data, update the cache
            data = data.split('\t')
            for i in range(2, 8, 2):
                self.m_countValuesCache[data[i]] = int(data[i + 1])
            # Reset no response count
            self.m_nNonResponse = 0
        else:
            self.NoResponse('No data after updating cache.\n'
                            'Suggestions:\n'
                            '\t- Serial cable might be unplug.\n'
                            '\t- Sensor power is off.\n')

    def NoResponse(self, _msg):
        # Set cache to None
        for key in self.m_countValuesCache.keys():
            self.m_countValuesCache[key] = None
        # Error message if necessary
        self.m_nNonResponse += 1
        if (self.m_nNonResponse >= self.m_maxNonResponse and
                self.m_nNonResponse % 2400 == self.m_maxNonResponse):
            cfg.LogFromOtherThread(
                '%s did not respond %d times\n%s' % (self.m_name,
                                                     self.m_nNonResponse,
                                                     _msg),
                True)

    def CacheRead(self):
        return self.m_countValuesCache

    def CountRead(self, _key):
        return self.m_countValuesCache[_key]


class SysCompWETLabs(SysComp):
    ''' A WET Labs count variable based on analog var '''

    def __init__(self, _name, _vars, _helpline=''):
        SysComp.__init__(self, _name, _vars, WETLabs, _helpline)

    def FirstTimeOnline(self):
        for var in self.vars.values():
            var.FirstTimeOnline()


class SysVarCountWETLabs(SysVarAnalog):
    ''' A WET Labs count variable based on analog var '''

    def __init__(self, _name, _rangeCount, _key,
                 _compName='', _helpline='', _units='',
                 _PreSetFunc=None, _PostGetFunc=None):
        showEditBox = (_PreSetFunc is not None)
        SysVarAnalog.__init__(self, _name, _rangeCount, WETLabs,
                              _compName, _helpline, showEditBox,
                              _units, _PreSetFunc, _PostGetFunc)
        self.m_key = _key

    def FirstTimeOnline(self):
        self.GetController().m_countValuesCache[self.m_key] = None

    def GetFunc(self):
        return self.GetController().CountRead(self.m_key)

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
            print BB3_349.CacheRead()

    # Close connection
    BB3_349.Close()
