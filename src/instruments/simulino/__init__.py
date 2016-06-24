# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-15 14:19:09
# @Last Modified by:   nils
# @Last Modified time: 2016-06-24 10:57:12

from threading import Thread
from time import sleep, time
from random import Random

from instruments import Instrument


class Simulino(Instrument):
    '''
    Set frame for all instruments
    '''

    def __init__(self, _name, _cfg):
        Instrument.__init__(self, _name)

        # Init Parameters
        self.m_timeout = None  # in seconds
        self.m_rnd = {}
        self.m_seed = {}
        self.m_mu = {}    # mean
        self.m_sigma = {}  # standard deviation
        self.m_connect_need_port = False

        # Load & Check configuration
        if 'frequency' in _cfg.keys():
            self.m_timeout = 1 / _cfg['frequency']
        else:
            print('Missing frequency in ' + _name + '.')
            exit()
        if 'variables' in _cfg.keys():
            if any(_cfg['variables']):
                for var, val in _cfg['variables'].items():
                    self.m_cache[var] = None
                    if 'seed' in val.keys():
                        self.m_seed[var] = val['seed']
                    else:
                        self.m_seed[var] = None
                    if 'mu' in val.keys():
                        self.m_mu[var] = val['mu']
                    else:
                        print(_name + ':' + var + ' missing mu')
                        exit()
                    if 'sigma' in val.keys():
                        self.m_sigma[var] = val['sigma']
                    else:
                        print(_name + ':' + var + ' missing sigma')
                        exit()
                    if 'units' in val.keys():
                        self.m_units[var] = val['units']
                    else:
                        print(_name + ':' + var + ' missing units')
                        exit()
                    self.m_varnames.append(var)
            else:
                print('No variables in ' + _name + '.')
                exit()
        else:
            print('Missing variables in ' + _name + '.')
            exit()

        # Initialize random generators
        for var in self.m_seed.keys():
            if self.m_seed[var] is None:
                self.m_rnd[var] = Random()
            else:
                self.m_rnd[var] = Random(self.m_seed[var])

    def Connect(self, _port=None):
        # input _port not used
        self.m_thread = Thread(target=self.RunUpdateCache, args=())
        self.m_thread.daemon = True
        self.m_active = True
        self.m_thread.start()
        return True

    def Close(self):
        # Stop thread updating cache
        if self.m_thread is not None:
            self.m_active = False
            if self.m_thread.isAlive():
                self.m_thread.join(self.m_timeout * 1.1)
            else:
                print(self.m_name + ' already close.')
        # Empty cache
        self.EmptyCache()

    def RunUpdateCache(self):
        start_time = time()
        while(self.m_active):
            try:
                sleep(self.m_timeout - (time() - start_time) % self.m_timeout)
                self.UpdateCache()
                self.m_n += 1
            except:
                print(self.m_name + ': Unexpected error while updating cache.')
                try:
                    self.EmptyCache()
                    self.m_nNoResponse += 1
                except Exception as e:
                    print(self.m_name +
                          ': Unexpected error while emptying cache')
                    print(e)

    def UpdateCache(self):
        # Update cache
        #   To be implemented by subclass
        pass
