# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-15 14:19:09
# @Last Modified by:   nils
# @Last Modified time: 2016-05-25 02:30:14

from threading import Thread
from time import sleep
from random import Random

from instruments import Instrument


class Simulino(Instrument):
    '''
    Set frame for all instruments
    '''

    # Parameters
    m_thread = None
    m_timeout = None  # in seconds
    m_rnd = {}
    m_cache = {}
    m_seed = {}
    m_mu = {}    # mean
    m_sigma = {}  # standard deviation

    def __init__(self, _name, _cfg):
        Instrument.__init__(self, _name)
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
        while(self.m_active):
            sleep(self.m_timeout)
            try:
                self.UpdateCache()
            except:
                print('Unexpected error while updating cache.')
                try:
                    for var in self.m_cache.keys():
                        self.m_cache[var] = None
                except:
                    print('Unexpected error while emptying cache')

    def UpdateCache(self):
        # Update cache
        #   To be implemented by subclass
        pass

    def ReadCache(self):
        # Return dictionnary with values in cache
        return self.m_cache

    def ReadVar(self, _key):
        # Return value in cache corresponding to the key
        return self.m_cache[_key]

    # def __del__(self):
    #     print('Simulino.__del__')
    #     Instrument.__del__(self)
