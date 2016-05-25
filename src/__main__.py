# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-22 17:21:16
# @Last Modified by:   nils
# @Last Modified time: 2016-05-24 23:28:36

import os
import sys

from __init__ import Inlinino


if len(sys.argv) == 2:
    Inlinino(sys.argv[1])
else:
    Inlinino(os.path.join('src', 'cfg', 'simulino_cfg.json'))
