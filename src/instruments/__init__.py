# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-15 12:11:42
# @Last Modified by:   nils
# @Last Modified time: 2017-01-15 17:53:25

# import sys
# import glob
from time import sleep
import serial.tools.list_ports


class Instrument(object):
    '''
    Set frame for all instruments
    '''

    def __init__(self, _name):
        # Init Parameters
        self.m_name = _name
        self.m_cache = {}
        self.m_units = {}
        self.m_varnames = []
        self.m_cacheIsNew = {}
        self.m_active = False
        self.m_connect_need_port = None
        self.m_thread = None

        # Count data logged
        self.m_n = 0
        self.m_nNoResponse = 0

    def Connect(self, _port=None):
        # Connect to instrument
        #   To be implemented by subclass
        #   if succesful connection to the instrument,
        #   it should switch state of member variable m_active to True
        #
        # RETURN:
        #   True    Succesful connection to the instrument
        #   False   Failed conection to the instrument
        pass

    def Close(self):
        # Close connection with instrument
        #   To be implemented by subclass
        #   it should switch state of member variable m_active to False
        pass

    def RunUpdateCache(self):
        while(self.m_active):
            try:
                self.UpdateCache()
            except Exception as e:
                print(self.m_name +
                      ': Unexpected error while updating cache.\n' +
                      'Suggestions:\n' +
                      '\t-Arduino board might be unplug\n' +
                      '\t-No data sent by the device\n')
                sleep(self.m_serial.timeout)
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

    def EmptyCache(self):
        for key in self.m_cache.keys():
            self.m_cache[key] = None

    def ReadCache(self):
        # Return dictionary with values in cache
        return self.m_cache

    def ReadVar(self, _key):
        # Return value in cache corresponding to the key only if the value was
        # updated since last read
        if self.m_cacheIsNew[_key]:
            self.m_cacheIsNew[_key] = False
            return self.m_cache[_key]
        else:
            return None

    def __str__(self):
        if self.m_active:
            return self.m_name + '[active]'
        else:
            return self.m_name + '[close]'

    # def __del__(self):
    #     # Thread must be closed before __del__ happen
    #     print('Instrument.__del__')


class Communication():

    m_port_list = []

    def __init__(self, _robust=False):
        # self.ListPorts()
        self.robust = _robust

    def ListPorts(self):
        # Method working on Python 2.7
        # pyserial version 2.7-py34_0 (default from conda) not working OSX py34
        # pyserial version 3.1.1-py3.4 (2016-06-12) is working on OSX py34
        self.m_port_list = serial.tools.list_ports.comports()

        # Method from Thomas (http://stackoverflow.com/users/300783/thomas)
        # Found on http://stackoverflow.com/questions/12090503
        # if sys.platform.startswith('win'):
        #     ports = ['COM%s' % (i + 1) for i in range(256)]
        # elif (sys.platform.startswith('linux') or
        #       sys.platform.startswith('cygwin')):
        #     # this excludes your current terminal "/dev/tty"
        #     ports = glob.glob('/dev/tty[A-Za-z]*')
        # elif sys.platform.startswith('darwin'):
        #     ports = glob.glob('/dev/tty.*')
        # else:
        #     raise EnvironmentError('Unsupported platform')

        # self.m_port_list = []
        # for port in ports:
        #     try:
        #         if self.robust:
        #             s = serial.Serial(port)
        #             s.close()
        #         self.m_port_list.append(port)
        #     except (OSError, serial.SerialException):
        #         pass

        return self.m_port_list

    # Compatible with serial.tools.list_ports.comports() only
    def PortInfo(self, _index):
        foo = self.m_port_list[_index].device + ': ' + \
            self.m_port_list[_index].description
        if self.m_port_list[_index].manufacturer is not None:
            foo += ' ' + self.m_port_list[_index].manufacturer
        if self.m_port_list[_index].product is not None:
            foo += ' ' + self.m_port_list[_index].product
        return foo

    def GetPortList(self):
        l = []
        for port in self.m_port_list:
            l.append(port.device)
        return l
        # return self.m_port_list

    def __str__(self):
        foo = ''
        for i in range(0, len(self.m_port_list)):
            foo += self.PortInfo(i) + '\n'
            # foo += self.m_port_list[i] + '\n'
        return foo[0:-1]

if __name__ == "__main__":
    com = Communication()
    com.ListPorts()
    print(com)
