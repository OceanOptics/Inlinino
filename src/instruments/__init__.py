# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-15 12:11:42
# @Last Modified by:   nils
# @Last Modified time: 2016-05-24 22:35:38


class Instrument():
    '''
    Set frame for all instruments
    '''

    # Parameters
    m_name = None
    m_timeout = None  # in seconds
    m_active = False

    def __init__(self, _name, _cfg):
        # Set configuration
        self.m_name = _name
        if 'frequency' in _cfg.keys():
            self.m_timeout = 1 / _cfg['frequency']  # frequency is in seconds
        else:
            print('Missing parameter frequency in cfg file for ' + _name + '.')
            exit()

    def Connect(self):
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

    def ReadCache(self):
        # Return dictionnary with values in cache
        #   To be implemented by subclass
        pass

    def __str__(self):
        if self.m_active:
            return self.m_name + '[active]'
        else:
            return self.m_name + '[close]'

    # def __del__(self):
    #     # Thread must be closed before __del__ happen
    #     print('Instrument.__del__')
