import logging
import sys
from multiprocessing import freeze_support


if __name__ == '__main__':
    freeze_support()

    from inlinino.gui import App
    inlinino = App([])

    # Get instrument selected
    if len(sys.argv) == 2:
        try:
            inlinino.start(int(sys.argv[1]))
        except ValueError as e:
            # raise e
            logging.critical('Invalid arguments.')
            logging.debug(e)
    else:
        inlinino.start()
