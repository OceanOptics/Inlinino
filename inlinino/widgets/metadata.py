from pyqtgraph.Qt import QtCore, QtWidgets

from inlinino.widgets import GenericWidget


class MetadataWidget(GenericWidget):
    def __init__(self, instrument):
        super().__init__(instrument)
        self.instrument.signal.new_meta_data.connect(self.on_new)

    def setup(self):
        items = []
        for key, values in self.instrument.widget_metadata_keys:
            item = QtWidgets.QTreeWidgetItem([key, '0'])
            for value in values:
                item.addChild(QtWidgets.QTreeWidgetItem([value, ' ']))
            items.append(item)
        self.tree_widget_metadata.clear()
        self.tree_widget_metadata.addTopLevelItems(items)
        # self.tree_widget_metadata.resizeColumnToContents(0)
        # self.tree_widget_metadata.setColumnWidth(1, 20)  # To prevent expanding too much on first show
        # self.tree_widget_metadata.expandAll()
        self.tree_widget_metadata.show()

    def reset(self):
        self.clear()

    @QtCore.pyqtSlot(list)
    def on_new(self, data):
        root = self.tree_widget_metadata.invisibleRootItem()
        for parent_idx, (parent_value, child_values) in enumerate(data):
            if root.child(parent_idx) is None:
                continue
            if parent_value is not None:
                root.child(parent_idx).setText(1, str(parent_value))
            if child_values is not None:
                for child_idx, child_value in enumerate(child_values):
                    root.child(parent_idx).child(child_idx).setText(1, str(child_value))

    def clear(self):
        self.instrument.widget_metadata_frame_counters = [0] * len(self.instrument.widget_metadata_frame_counters)
        root = self.tree_widget_metadata.invisibleRootItem()
        for parent_idx, counter in enumerate(self.instrument.widget_metadata_frame_counters):
            if root.child(parent_idx) is not None:
                root.child(parent_idx).setText(1, str(counter))
