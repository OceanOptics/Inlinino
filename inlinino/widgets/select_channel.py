from pyqtgraph.Qt import QtCore, QtGui

from inlinino.widgets import GenericWidget


class SelectChannelWidget(GenericWidget):
    expanding = True

    def __init__(self, instrument):
        # Set Data Model & Filter Proxy Model
        self.variables_model = QtGui.QStandardItemModel()
        self.variables_filter_proxy_model = QtCore.QSortFilterProxyModel()
        self.variables_filter_proxy_model.setSourceModel(self.variables_model)
        self.variables_filter_proxy_model.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        # Setup
        super().__init__(instrument)
        # Connect Search Field to Filter Proxy Model
        self.variables_search.textChanged.connect(self.variables_filter_proxy_model.setFilterRegExp)
        # Add Data Filter Proxy Model to List View
        self.list_variables.setModel(self.variables_filter_proxy_model)
        self.list_variables.clicked.connect(self.update)

    def setup(self):
        # Clear Past Variables
        self.variables_model.clear()
        # Set Current Variables
        for v in self.instrument.widget_active_timeseries_variables_names:
            item = QtGui.QStandardItem(v)
            item.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            if v in self.instrument.widget_active_timeseries_variables_selected:
                item.setData(QtCore.QVariant(QtCore.Qt.Checked), QtCore.Qt.CheckStateRole)
            else:
                item.setData(QtCore.QVariant(QtCore.Qt.Unchecked), QtCore.Qt.CheckStateRole)
            self.variables_model.appendRow(item)
        # Clear Search field
        self.variables_search.setText('')

    def reset(self):
        self.setup()

    @QtCore.pyqtSlot(QtCore.QModelIndex)
    def update(self, proxy_index):
        source_index = self.variables_filter_proxy_model.mapToSource(proxy_index).row()
        self.instrument.update_active_timeseries_variables(
            self.variables_model.item(source_index).text(),
            bool(self.variables_model.item(source_index).checkState())
        )
