# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-14 16:55:10
# @Last Modified by:   nils
# @Last Modified time: 2016-06-20 13:16:20

import os
import json
from collections import OrderedDict


class Cfg():
    '''
    Class to load and set to default all variables from the software
    '''
    # Set to None cfg variables
    m_v = 1
    m_path_app = None
    m_app = None
    m_instruments = None

    def __init__(self):
        # Load default configuration file
        self.m_path_app = os.path.dirname(os.path.realpath(__file__))
        cfgFile = os.path.join(self.m_path_app, 'cfg', 'default_cfg.json')
        if not self.Load(cfgFile):
            if self.m_v > 0:
                print('Unable to load default configuration file.')

    def Load(self, _filename):
        # Load configuration from json file
        with open(_filename) as data_file:
            d = json.load(data_file, object_pairs_hook=OrderedDict)
            if 'app_cfg' in d.keys():
                self.m_app = d['app_cfg']
                if 'verbosity' in self.m_app.keys():
                    self.m_v = self.m_app['verbosity']
            if 'instruments' in d.keys():
                self.m_instruments = d['instruments']
            return True
        return False

    def Check(self):
        # Check that all the required parameters are defined
        if (self.m_app is None or self.m_instruments is None):
            if self.m_v > 0:
                print('Missing elements in configuration file.')
            return False
        return True

    def __str__(self):
        return '[Configuration]\n\tverbosity:' + str(self.m_v)
        # print('App', self.m_app)
        # print('Log', self.m_log)
        # print('Instruments', self.m_instruments)

# Test class Cfg
if __name__ == '__main__':
    cfg = Cfg()
    cfg.Load(os.path.join('cfg_deprecated/simulino_cfg.json'))
    print(cfg)
    print('Pass check:', cfg.Check())
