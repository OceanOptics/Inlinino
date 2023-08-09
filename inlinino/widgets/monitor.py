from pyqtgraph.Qt import QtCore, QtGui

from inlinino.widgets import GenericWidget


class MonitorWidget(GenericWidget):

    def __init__(self, instrument):
        super().__init__(instrument)
        # Connect signals and triggers
        self.instrument.interface_signal.read.connect(self.update_monitor)
        self.instrument.interface_signal.write.connect(self.update_monitor)
        self.command_field.returnPressed.connect(self.send_command)
        self.send_button.clicked.connect(self.send_command)
        # Set console
        self.monitor_view.setMaximumBlockCount(80)  # Maximum number of lines in console

    def setup(self):
        pass

    def clear(self):
        self.monitor_view.clear()

    @QtCore.pyqtSlot(bytes)
    def update_monitor(self, data: bytes):
        data.replace(b'\r', b'')  # Use only \n otherwise create extra line
        self.monitor_view.moveCursor(QtGui.QTextCursor.End)
        self.monitor_view.insertPlainText(data.decode('utf8', errors='replace'))
        self.monitor_view.moveCursor(QtGui.QTextCursor.StartOfLine)

    def send_command(self):
        cmd = self.command_field.text()
        if not cmd:
            self.instrument.signal.warning.emit('No command to send (field empty).')
        elif self.instrument.send_cmd(cmd):
            self.command_field.setText('')
