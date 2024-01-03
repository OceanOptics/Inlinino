import os
import re

from pyqtgraph.Qt import QtWidgets, QtGui, QtCore, uic

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


class GenericDialog(QtWidgets.QDialog):

    @classproperty
    def __snake_name__(cls) -> str:
        return re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()

    def __init__(self, parent=None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        if parent is not None and parent.isActiveWindow():
            self.setWindowModality(QtCore.Qt.WindowModal)
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, f'dialog_{self.__snake_name__[:-7]}.ui'), self)
        self.run_button = self.button_box.addButton("Run", QtGui.QDialogButtonBox.ActionRole)
        self.run_button.clicked.connect(self.start)
        self.button_box.button(QtGui.QDialogButtonBox.Close).clicked.connect(self.accept)

    def disable_run_button(self, text='Processing ...'):
        self.run_button.setText(text)
        self.run_button.setEnabled(False)

    def enable_run_button(self):
        self.run_button.setText('Run')
        self.run_button.setEnabled(True)

    def check_fields_passed(self, ignore=None):
        ignore = ignore if ignore is not None else []
        for f in [f for f in self.__dict__.keys() if f.startswith('le_')]:
            if f in ignore:
                continue
            if not getattr(self, f).text():
                self.instrument.signal.warning.emit('All fields must be field.')
                return False
        return True


