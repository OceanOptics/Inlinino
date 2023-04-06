from pyqtgraph.Qt import QtGui

class FileLabel():
    def __init__(self, qt_label: QtGui.QLabel):
        self.qt_label = qt_label
        self.absolute_file_path = None
        self.qt_label.setText('')

    def set_file(self, absolute_file_path):
        self.absolute_file_path = absolute_file_path
        self.qt_label.setText(absolute_file_path.split('/')[-1])

    def get_file(self):
        return self.absolute_file_path
