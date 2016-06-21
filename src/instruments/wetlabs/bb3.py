# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 19:00:56
# @Last Modified by:   nils
# @Last Modified time: 2016-06-21 11:46:23


from instruments.wetlabs import WETLabs


class BB3(WETLabs):



    def __init__(self, _name, _cfg):
        WETLabs.__init__(self, _name, _cfg)

        # Init parameters
        self.m_varname_header=None
        self.m_lambda=[]

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


    def UpdateCache(self):
        # read all line in buffer
        data = self.m_serial.readlines()
        if data:
            # keep only most recent data
            data = data[-1]
            # There is data, update the cache
            # print(data)
            data = data.split('\t')
            for i in range(2, 8, 2):
                self.m_cache[self.m_varname_header + data[i]] = int(data[i + 1])
        else:
            self.NoResponse()
