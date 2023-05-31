import os
import re

from pyqtgraph.Qt import QtWidgets, uic

from inlinino import PATH_TO_RESOURCES


class classproperty(property):
    def __get__(self, owner_self, owner_cls):
        return self.fget(owner_cls)


class GenericWidget(QtWidgets.QWidget):
    expanding = False

    @classproperty
    def __snake_name__(cls) -> str:
        return re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()

    def __init__(self, instrument=None):
        # Load pyQt interface
        super().__init__()
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, f'widget_{self.__snake_name__[:-7]}.ui'), self)
        # Pointer to instrument to control
        self.instrument = instrument
        # Setup widget
        self.setup()

    def setup(self):
        raise NotImplementedError()

    def reset(self):
        pass

    def clear(self):
        pass

    def counter_reset(self):
        pass
