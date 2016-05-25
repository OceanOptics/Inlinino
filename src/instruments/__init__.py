# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-15 12:11:42
# @Last Modified by:   nils
# @Last Modified time: 2016-05-25 02:02:39

from serial.tools import list_ports


class Instrument():
    '''
    Set frame for all instruments
    '''

    # Parameters
    m_name = None
    m_cache = {}
    m_active = False

    def __init__(self, _name):
        # Set configuration
        self.m_name = _name

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

    def EmptyCache(self):
        for key in self.m_cache.keys():
            self.m_cache[key] = None

    def ReadCache(self):
        return self.m_cache

    def ReadVar(self, _key):
        return self.m_cache[_key]

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

    def __init__(self):
        self.ListPorts()

    def ListPorts(self):
        self.m_port_list = list_ports.comports()

    def PortInfo(self, _index):
        foo = self.m_port_list[_index].device + ': ' + \
            self.m_port_list[_index].description
        if self.m_port_list[_index].manufacturer is not None:
            foo += ' ' + self.m_port_list[_index].manufacturer
        if self.m_port_list[_index].product is not None:
            foo += ' ' + self.m_port_list[_index].product
        return foo

    def __str__(self):
        foo = ''
        for i in range(0, len(self.m_port_list)):
            foo += self.PortInfo(i) + '\n'
        return foo[0:-1]
