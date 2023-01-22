import os

from pyqtgraph.Qt import QtWidgets, uic

from inlinino import PATH_TO_RESOURCES


class GenericPlugin(QtWidgets.QWidget):

    def __init__(self, instrument=None):
        # Load pyQt interface
        super().__init__()
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, f'widget_{self.__class__.__name__.lower()[:-6]}.ui'), self)
        # App variables
        self.instrument = instrument
        self.setup()
        self.active = True

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def show(self):
        if not self.active:
            self.setup()
            self.active = True

    def hide(self):
        self.active = False

    def setup(self):
        raise NotImplementedError()
