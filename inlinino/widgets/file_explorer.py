import os
from time import sleep

from pyqtgraph.Qt import QtWidgets, QtCore, QtGui, uic
import wakepy

from inlinino import PATH_TO_RESOURCES
from inlinino.shared.tree import QFileItem
from inlinino.instruments.hypernav import HyperNav
from inlinino.widgets import GenericWidget, classproperty


class FileExplorerWidget(GenericWidget):
    @classproperty
    def __snake_name__(self):
        return 'file_explorer_widget'

    def __init__(self, instrument: HyperNav):
        super().__init__(instrument)

        self.model = QRemoteFileSystemModel(self.instrument.local_file_system.fs)
        self.tree_view.setModel(self.model)
        self.tree_view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree_view.selectionModel().selectionChanged.connect(self.handle_selection)

        self.instrument.signal.toggle_command_mode.connect(self.toggle_buttons)
        self.instrument.signal.cmd_list.connect(self.update_file_explorer)
        # self.model.dataChanged.connect(self.update_tree_view)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_download.clicked.connect(self.download)
        # self.btn_delete.clicked.connect(self.delete)

    def setup(self):
        self.toggle_buttons(self.instrument.command_mode)

    @QtCore.pyqtSlot(bool)
    def toggle_buttons(self, enable):
        self.btn_refresh.setEnabled(enable)
        self.btn_download.setEnabled(enable)
        # self.btn_delete.setEnabled(enable)

    def refresh(self, cmd):
        self.instrument.local_file_system.reset()
        self.instrument.send_cmd('list')

    @QtCore.pyqtSlot()
    def update_file_explorer(self):
        path = self.instrument.local_file_system.explore()
        if path:
            # Keep exploring
            self.instrument.send_cmd(f'list {path}', check_timing=False)
        else:
            # Reload entire model
            self.model = QRemoteFileSystemModel(self.instrument.local_file_system.fs)
            self.tree_view.selectionModel().selectionChanged.disconnect(self.handle_selection)  # signal doesn't carry when change model
            self.tree_view.setModel(self.model)
            self.tree_view.expandAll()
            self.tree_view.resizeColumnToContents(0)
            self.handle_selection(None, None)  # reset selection
            self.tree_view.selectionModel().selectionChanged.connect(self.handle_selection) # reconnect to new model
            # TODO Figure out method to update model instead of reloading model
            #      http://pharma-sas.com/common-manipulation-of-qtreeview-using-pyqt5/

    def handle_selection(self, selected, deselected):
        items = [i for i in self.tree_view.selectedIndexes() if i.column() == 0]
        self.btn_download.setText(f"Download {f'[{len(items)}]' if len(items) > 0 else ''}" )
        # self.btn_delete.setText(f"Delete {f'[{len(items)}]' if len(items) > 0 else ''}")

    def download(self):
        items = [i.internalPointer() for i in self.tree_view.selectedIndexes() if i.column() == 0]
        if len(items) < 1:
            msg = QtGui.QMessageBox(QtWidgets.QMessageBox.Warning, "Download File(s)",
                                    f"Nothing to download, please select files to download first.",
                                    QtGui.QMessageBox.Close, self)
            msg.setWindowModality(QtCore.Qt.WindowModal)
            msg.exec_()
            return
        msg = QtGui.QMessageBox(QtWidgets.QMessageBox.Question, "Download File(s)",
                                f"Are you sure you want to download the {len(items)} file(s) selected?",
                                QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, self)
        msg.setWindowModality(QtCore.Qt.WindowModal)
        if msg.exec_() == QtGui.QMessageBox.Yes:
            dialog = DialogDownloadFiles(self, items)
            status = dialog.exec_()
            if not dialog.exec_():  # 0: reject | 1: accept
                # User cancelled
                self.instrument.signal.warning.emit(
                    'Data download cancelled. HyperNav is still transmitting data, '
                    'wait for prompt to appear in "Serial Monitor" or power cycle HyperNav '
                    'before sending new commands\n'
                )
    #
    # def delete(self):
    #     raise NotImplementedError('Not Implemented.')


class DialogDownloadFiles(QtGui.QDialog):
    def __init__(self, parent, items):
        # p = parent
        # while not isinstance(p, QtGui.QMainWindow):
        #     p = p.parent()
        super().__init__(parent)
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, 'dialog_download_files.ui'), self)
        self.instrument = parent.instrument
        self.items = items
        self.idx = 0

        self.button_box.button(QtGui.QDialogButtonBox.Close).clicked.connect(self.accept)
        self.button_box.button(QtGui.QDialogButtonBox.Cancel).clicked.connect(self.reject)
        self.instrument.signal.cmd_list.connect(self.expand_folder)
        self.instrument.signal.cmd_dump.connect(self.next)

        self.button_box.button(QtGui.QDialogButtonBox.Close).setEnabled(False)

        # Prevent computer to sleep
        wakepy.set_keepawake(keep_screen_awake=False)
        # Start downloading files
        self.next()

    # def closeEvent(self, *args):
    #     self.instrument.signal.cmd_list.disconnect(self.expand_folder)
    #     self.instrument.signal.cmd_dump.disconnect(self.next)
    #     # super().done(*args)

    @QtCore.pyqtSlot(int)
    def next(self, status: int = None):
        self.view.moveCursor(QtGui.QTextCursor.End)
        if status == -1:  # Folder expanded
            self.view.insertPlainText(' Done\n')
        elif status == -2:  # Error while downloading file
            self.view.insertPlainText(' Error\n')
        elif status is not None:  # File downloaded (got size)
            self.view.insertPlainText(f' {status}/{self.items[self.idx-1].size} B\n')
        if self.idx < len(self.items):
            item = self.items[self.idx]
            path = self.instrument.local_file_system.join(*item.path())
            if item.is_dir:
                self.view.insertPlainText(f'Expanding folder {path} ... ')
                self.instrument.send_cmd(f'list {path}', check_timing=False)
                # expand_folder is called on reply to list
            else:
                self.instrument.send_cmd(f'dump * {path}', check_timing=False)
                self.view.insertPlainText(f'Downloading {path} ... ')
                self.idx += 1
            self.view.moveCursor(QtGui.QTextCursor.StartOfLine)
        else:
            if self.idx != 0:
                self.view.insertPlainText('All files downloaded.\n')
            else:
                self.view.insertPlainText('Nothing to download.\n')
            self.button_box.button(QtGui.QDialogButtonBox.Close).setEnabled(True)
            wakepy.unset_keepawake()

    @QtCore.pyqtSlot()
    def expand_folder(self):
        # Assume command list was sent from next (Present dialog block serial monitor)
        # Append files listed in most recent folder to list
        self.items = self.items[:self.idx+1] + self.items[self.idx].files + self.items[self.idx+1:]
        # Resume download t the next file
        self.idx += 1
        self.next(-1)


class QItemModel(QtCore.QAbstractItemModel):
    def __init__(self, item_tree):
        super().__init__()
        self._root = item_tree

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = None) -> QtCore.QModelIndex:
        p = self._root if not parent or not parent.isValid() else parent.internalPointer()
        if not QtCore.QAbstractItemModel.hasIndex(self, row, column, parent):
            return QtCore.QModelIndex()

        child = p.child(row)
        if child:
            return QtCore.QAbstractItemModel.createIndex(self, row, column, child)
        else:
            return QtCore.QModelIndex()

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if child.isValid():
            parent = child.internalPointer().parent()
            if parent:
                return QtCore.QAbstractItemModel.createIndex(self, parent.row(), 0, parent)
        return QtCore.QModelIndex()

    def rowCount(self, parent: QtCore.QModelIndex) -> int:
        if parent.isValid():
            return parent.internalPointer().childCount()
        return self._root.childCount()

    def columnCount(self, parent: QtCore.QModelIndex) -> int:
        if parent.isValid():
            return parent.internalPointer().columnCount()
        return self._root.columnCount()

    def data(self, index: QtCore.QModelIndex, role: int):
        if not index.isValid():
            return None
        item = index.internalPointer()
        if role == QtCore.Qt.DisplayRole:
            return item.data(index.column())
        return None


class QRemoteFileSystemModel(QItemModel):

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole and section < len(QFileItem.HEADER):
            return QFileItem.HEADER[section]
        return super().headerData(section, orientation, role)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        # if index.column() == 0:
        #     return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsUserCheckable
        if index.internalPointer().is_dir and index.internalPointer().childCount() != 0:
            return QtCore.Qt.ItemIsEnabled
        else:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    # Methods from QtWidgets.QFileSystemModel
    # def fileInfo(self):
    #     pass

    def fileName(self, index: QtCore.QModelIndex):
        return index.internalPointer().name

    def filePath(self, index: QtCore.QModelIndex):
        return index.internalPointer().path()

    def isDir(self, index: QtCore.QModelIndex):
        return index.internalPointer().is_dir
