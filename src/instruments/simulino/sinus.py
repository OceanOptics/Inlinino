# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-15 14:20:53
# @Last Modified by:   nils
# @Last Modified time: 2016-06-21 12:09:49

from instruments.simulino import Simulino
from math import sin


class Sinus(Simulino):

    def __init__(self, _name, _cfg):
        Simulino.__init__(self, _name, _cfg)
        self.m_x = {}
        self.m_step = {}
        for var, val in _cfg['variables'].items():
            if 'step' in val.keys():
                self.m_step[var] = val['step']
            else:
                print(_name + ':' + var + ' missing step')
                exit()
            if 'start' in val.keys():
                self.m_x[var] = val['start']
            else:
                print(_name + ':' + var + ' missing start')
                exit()

    def UpdateCache(self):
        for var in self.m_cache.keys():
            self.m_cache[var] = sin(self.m_x[var]) + self.m_rnd[var].gauss(
                self.m_mu[var], self.m_sigma[var])
            self.m_x[var] += self.m_step[var]
