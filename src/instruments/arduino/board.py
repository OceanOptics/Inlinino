# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 16:22:19
# @Last Modified by:   nils
# @Last Modified time: 2016-07-05 12:30:18


from instruments.arduino import Arduino


class Board(Arduino):

    def __init__(self, _name, _cfg):
        Arduino.__init__(self, _name, _cfg)

    def SetConfiguration(self, _check=b''):
        # Set configuration of Arduino board
        if _check is b'' or _check == b'sample_rate<int>\r\n':
            self.m_serial.write(bytes(str(self.m_frequency), 'UTF-8'))
            return True
        else:
            return False
