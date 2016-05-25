# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 19:00:56
# @Last Modified by:   nils
# @Last Modified time: 2016-05-25 02:20:05


from instruments.wetlabs import WETLabs


class BB3(WETLabs):

    m_varname_header=None
    m_lambda=[]

    def __init__(self, _name, _cfg):
        WETLabs.__init__(self, _name, _cfg)

        # Load cfg
        if 'varname_header' in _cfg.keys():
            self.m_varname_header = _cfg['varname_header']
        else:
            print('Missing varname_header in ' + _name + '.')
        if 'lambda' in _cfg.keys():
            self.m_lambda = _cfg['lambda']
        else:
            print('Missing lambda in ' + _name + '.')

        # Init cache in case log starts before instrument is connected
        for l in self.m_lambda:
            self.m_cache[self.m_varname_header + str(l)] = None


    def UpdateCache(self):
        # read all line in buffer
        data = self.m_serial.readlines()
        if data:
            # keep only most recent data
            data = data[-1]
            # There is data, update the cache
            data = data.split('\t')
            for i in range(2, 8, 2):
                self.m_cache[self.m_varname_header + data[i]] = int(data[i + 1])
            # Reset no response count
            self.m_nNonResponse = 0
        else:
            self.NoResponse('No data after updating cache.\n' +
                            'Suggestions:\n' +
                            '\t- Serial cable might be unplug.\n' +
                            '\t- Sensor power is off.\n')
