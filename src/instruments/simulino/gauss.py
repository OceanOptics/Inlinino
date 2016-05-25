# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-15 14:20:53
# @Last Modified by:   nils
# @Last Modified time: 2016-05-24 22:34:38

from time import sleep

from instruments.simulino import Simulino


class Gauss(Simulino):

    def __init__(self, _name, _cfg):
        Simulino.__init__(self, _name, _cfg)

    def UpdateCache(self):
        for var in self.m_cache.keys():
            self.m_cache[var] = self.m_rnd[var].gauss(
                self.m_mu[var], self.m_sigma[var])

    # def __del__(self):
    #     print('Gauss.__del__')
    #     Simulino.__del__(self)

# Example of use
if __name__ == '__main__':
    simulation = Gauss('Simulation', {
        "module": "simulino",
        "name": "gauss",
        "frequency": 10,
        "variables": {
            "rnd1": {
                "mu": 2.5,
                "sigma": 1,
                "seed": 1,
                "units": "No Units"
            },
            "rnd2": {
                "mu": 0.5,
                "sigma": 0.2,
                "seed": 2,
                "units": "No Units"
            }
        }
    })

    # Connect with port
    simulation.Connect()
    sleep(1)

    if simulation.m_active:
        # UpdateCache 10 times
        for i in range(1, 10):
            sleep(simulation.m_timeout)
            print(simulation.ReadCache())

    # Close connection
    # simulation.Close()
