# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-22 17:21:16
# @Last Modified by:   nils
# @Last Modified time: 2016-06-27 11:08:50

import logging
import sys
from inlinino.gui import App

inlinino = App([])

# Get instrument selected
if len(sys.argv) == 2:
    try:
        inlinino.start(int(sys.argv[1]))
    except ValueError:
        logging.critical('Invalid arguments.')
else:
    inlinino.start()
