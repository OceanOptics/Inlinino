# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2017-01-15 18:03:11
# @Last Modified by:   nils
# @Last Modified time: 2017-01-16 14:48:09


from instruments.wetlabs import WETLabs
import numpy as np
# from time import time, gmtime, strftime  # for debugging only


class UBAT(WETLabs):

    def __init__(self, _name, _cfg):
        WETLabs.__init__(self, _name, _cfg)

        # Specific configuration variables
        self.m_vardisplayed = dict()
        self.m_vartype = dict()

        # Load specific cfg
        if 'logged' in _cfg.keys():
            self.m_varlogged = _cfg['logged']
        else:
            if __debug__:
                print(_name + ': Missing logged')
            self.m_varlogged = [True for i in range(len(self.m_lambda))]
        if 'displayed' in _cfg.keys():
            var_displayed = _cfg['displayed']
        else:
            if __debug__:
                print(_name + ': Missing displayed')
            var_displayed = [True for i in range(len(self.m_lambda))]
        if 'type' in _cfg.keys():
            var_type = _cfg['type']
        else:
            if __debug__:
                print(_name + ': Missing displayed')
            exit()

        # Check size of arrays
        if len(self.m_lambda) != len(self.m_varlogged) or \
                len(self.m_lambda) != len(var_displayed) or \
                len(self.m_lambda) != 11:
            print(_name + ': arrays logged, displayed and lambda ' +
                  'have a size different than 11')
            print(len(self.m_lambda), self.m_lambda)
            print(len(self.m_varlogged), self.m_varlogged)
            print(len(var_displayed), var_displayed)
            exit()

        # Update cache removing non logged variables
        # A variable not logged won't be displayed
        varnames_buffer = list(self.m_varnames)
        for i in range(len(self.m_lambda)-1, -1, -1): # Start by end of list
            if not self.m_varlogged[i]:
                # Remove variable not logged
                varname = self.m_varnames.pop(i)
                del self.m_cache[varname]
                del self.m_cacheIsNew[varname]
                del self.m_units[varname]
            else:
                # Add parameter for variable displayed
                self.m_vardisplayed[varnames_buffer[i]] = var_displayed[i]
                # Add type of variable (str, int, or float)
                self.m_vartype[varnames_buffer[i]] = var_type[i]


    def UpdateCache(self):
        # readline wait for \EOT or timeout and
        data = self.m_serial.readline()
        if data:
            # data is a byte array
            data = data[:-2].split(b',', 10)
            if len(data) == 11 and data[0][:4] == b'UBAT':
                # Get data
                for i in range(11):
                    if self.m_varlogged[i]:
                        varname = self.m_lambda[i] # can't use self.varnames because it's incomplete
                        # print(i, varname, self.m_vartype[varname], self.m_cache[varname])
                        if self.m_vartype[varname] == 'str':
                            self.m_cache[varname] = str(data[i])
                        elif self.m_vartype[varname] == 'int':
                            self.m_cache[varname] = int(data[i])
                        elif self.m_vartype[varname] == 'float':
                            self.m_cache[varname] = float(data[i])
                        elif self.m_vartype[varname] == 'array':
                            # 60 Hz digitized raw A/D counts
                            self.m_cache[varname] = str(data[i]).replace(',', ';')
                            # self.m_cache[varname] = [int(d) for d in data[i].split(b',')]
                            # print(self.m_cache[varname])
                        else:
                            # Unkow data type
                            self.CommunicationError('Unknow data type.\n' +
                                        'This is due to an error in the ' +
                                        'configuration file.\n The only data' +
                                        ' type available for a UBAT are:' +
                                        ' str, int, float, or list.')
                        self.m_cacheIsNew[varname] = True
                # Update counter
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
