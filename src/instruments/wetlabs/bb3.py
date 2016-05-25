# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 19:00:56
# @Last Modified by:   nils
# @Last Modified time: 2016-04-08 19:16:54

# WETLabs Sensor BB3
from __future__ import division
from instrumentino.controllers.wetlabs import SysCompWETLabs


class BB3(SysCompWETLabs):
    def __init__(self, _name, _countVars=()):
        SysCompWETLabs.__init__(
            self, _name, _countVars, "Set WET Labs count variables")
