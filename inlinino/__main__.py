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
