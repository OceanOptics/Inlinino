# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 16:22:19
# @Last Modified by:   nils
# @Last Modified time: 2016-06-24 16:26:26


from instruments.arduino import Arduino


class ADS1015(Arduino):

    m_gain_list = [23, 1, 2, 4, 8, 16]

    def __init__(self, _name, _cfg):
        Arduino.__init__(self, _name, _cfg)

        if 'gain' in _cfg.keys():
            if _cfg['gain'] in self.m_gain_list:
                self.m_gain = _cfg['gain']
            else:
                print(_name + ' invalid gain\n' +
                      'valid gain are 23, 1, 2, 4, 8, 16')
                exit()
        else:
            print(_name + ' missing gain')
            exit()

        # Record gain setting in units (which will be displayed in log file)
        if self.m_gain == 23:
            gain_str = '2/3'
        else:
            gain_str = str(self.m_gain)
        for k in self.m_units.keys():
            self.m_units[k] = gain_str + 'x ' + self.m_units[k]

    def SetConfiguration(self, _check=None):
        # Set configuration of Arduino board
        if _check is None or _check == b'sample_rate<int>\tgain<int>\r\n':
            self.m_serial.write(bytes(str(self.m_frequency) + '/t' +
                                      str(self.m_gain), 'UTF-8'))
            return True
        else:
            return False
