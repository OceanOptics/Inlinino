from pyqtgraph.Qt import QtCore, QtGui

from inlinino.widgets import GenericWidget


class AuxDataWidget(GenericWidget):

    def __init__(self, instrument):
        self.variable_names = []
        self.variable_values = []
        super().__init__(instrument)
        self.instrument.signal.new_aux_data.connect(self.on_new_aux_data)

    def setup(self):
        # Reset fields
        self.variable_names = []
        self.variable_values = []
        for i in reversed(range(self.group_box_aux_data_layout.count())):
            self.group_box_aux_data_layout.itemAt(i).widget().setParent(None)
        # Set aux variable names
        for v in self.instrument.widget_aux_data_variable_names:
            self.variable_names.append(QtGui.QLabel(v))
            self.variable_values.append(QtGui.QLabel('?'))
            self.group_box_aux_data_layout.addRow(self.variable_names[-1],
                                                  self.variable_values[-1])

    def reset(self):
        self.setup()

    @QtCore.pyqtSlot(list)
    def on_new_aux_data(self, data):
        for i, v in enumerate(data):
            self.variable_values[i].setText(str(v))
