import os
import sys
import glob
import logging
import uuid
import zipfile
import configparser
from math import floor
from time import time, gmtime, strftime
import serial
from serial.tools.list_ports import comports as list_serial_comports
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtCore, QtWidgets, uic
from PyQt5 import QtMultimedia
from pyACS.acs import ACS as ACSParser
import pySatlantic.instrument as pySat

from inlinino import RingBuffer, __version__, PATH_TO_RESOURCES, COLOR_SET
from inlinino.app_signal import InstrumentSignals, HyperNavSignals
from inlinino.cfg import CFG
from inlinino.instruments import Instrument, SerialInterface, SocketInterface, USBInterface, USBHIDInterface
from inlinino.instruments.acs import ACS
from inlinino.instruments.apogee import ApogeeQuantumSensor
from inlinino.instruments.dataq import DATAQ
from inlinino.instruments.hyperbb import HyperBB
from inlinino.instruments.hydroscat import HydroScat
from inlinino.instruments.hypernav import HyperNav, read_manufacturer_pixel_registration
from inlinino.instruments.lisst import LISST
from inlinino.instruments.nmea import NMEA
from inlinino.instruments.ontrak import Ontrak, USBADUHIDInterface
from inlinino.instruments.satlantic import Satlantic
from inlinino.instruments.suna import SunaV1, SunaV2
from inlinino.instruments.taratsg import TaraTSG
from inlinino.instruments.lisst import LISSTParser
from inlinino.widgets.aux_data import AuxDataWidget
from inlinino.widgets.flow_control import FlowControlWidget
from inlinino.widgets.hypernav import HyperNavCalWidget
from inlinino.widgets.metadata import MetadataWidget
from inlinino.widgets.pump_control import PumpControlWidget
from inlinino.widgets.select_channel import SelectChannelWidget


logger = logging.getLogger('GUI')


def seconds_to_strmmss(seconds):
    min = floor(seconds / 60)
    sec = seconds % 60
    return '%d:%02d' % (min, sec)


class MainWindow(QtGui.QMainWindow):
    BACKGROUND_COLOR = '#F8F8F2'
    FOREGROUND_COLOR = '#26292C'
    PEN_COLORS = COLOR_SET
    BUFFER_LENGTH = 240
    MAX_PLOT_REFRESH_RATE = 4   # Hz

    def __init__(self, instrument=None):
        super(MainWindow, self).__init__()
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, 'main.ui'), self)
        # Graphical Adjustments
        self.dock_widget_primary.setTitleBarWidget(QtGui.QWidget(None))
        self.dock_widget_secondary.setTitleBarWidget(QtGui.QWidget(None))
        self.label_app_version.setText('Inlinino v' + __version__)
        # Set Colors
        palette = QtGui.QPalette()
        palette.setColor(palette.Window, QtGui.QColor(self.BACKGROUND_COLOR))  # Background
        palette.setColor(palette.WindowText, QtGui.QColor(self.FOREGROUND_COLOR))  # Foreground
        self.setPalette(palette)
        pg.setConfigOption('background', pg.mkColor(self.BACKGROUND_COLOR))
        pg.setConfigOption('foreground', pg.mkColor(self.FOREGROUND_COLOR))
        # Set figure with pyqtgraph
        # pg.setConfigOption('antialias', True)  # Lines are drawn with smooth edges at the cost of reduced performance
        self._buffer_timestamp = None
        self._buffer_data = []
        self.reset_ts_trace = False
        self.last_timeseries_plot_refresh = time()
        self.timeseries_plot_widget = None
        self.last_spectrum_plot_refresh = time()
        self.spectrum_plot_widget = None
        # Set instrument
        if instrument:
            self.init_instrument(instrument)
        else:
            self.instrument = None
        self.packets_received = 0
        self.packets_logged = 0
        self.packets_corrupted = 0
        self.packets_corrupted_flag = False
        self.last_packet_corrupted_timestamp = 0
        # Set buttons
        self.button_setup.clicked.connect(self.act_instrument_setup)
        self.button_serial.clicked.connect(self.act_instrument_interface)
        self.button_log.clicked.connect(self.act_instrument_log)
        self.button_figure_clear.clicked.connect(self.act_clear)
        # Set clock
        self.signal_clock = QtCore.QTimer()
        self.signal_clock.timeout.connect(self.set_clock)
        self.signal_clock.start(1000)
        # Set Alarm: data timeout
        self.alarm_message_box = MessageBoxAlarm(self)
        # Widgets variables
        self.widget_metadata = None
        self.widgets = []

    def add_widget(self, widget, secondary_dock=True):
        self.widgets.append(widget(self.instrument))
        self.widgets[-1].layout.setContentsMargins(QtCore.QMargins(0, 0, 0, 0))
        if secondary_dock:
            self.docked_widget_secondary_layout.addWidget(self.widgets[-1])
        else:
            self.docked_widget_primary_layout.addWidget(self.widgets[-1])

    def toggle_secondary_dock(self, init=False):
        if self.instrument.secondary_dock_widget_enabled:
            if not self.dock_widget_secondary.isVisible() or init:
                self.resize(self.width() + 207, self.height())  # Bug expands vertically
                self.dock_widget_secondary.show()
        else:
            if self.dock_widget_secondary.isVisible() or init:
                if not init:
                    self.resize(self.width() - 207, self.height())
                self.dock_widget_secondary.hide()

    def init_instrument(self, instrument):
        self.instrument = instrument
        self.label_instrument_name.setText(self.instrument.short_name)
        # Set interface
        if self.instrument.interface_name.startswith('socket'):
            self.label_open_port.setText('Socket')
        elif self.instrument.interface_name.startswith('usb'):
            self.label_open_port.setText('USB Port')
        # Connect Signals
        self.instrument.signal.status_update.connect(self.on_status_update)
        self.instrument.signal.packet_received.connect(self.on_packet_received)
        self.instrument.signal.packet_corrupted.connect(self.on_packet_corrupted)
        self.instrument.signal.packet_logged.connect(self.on_packet_logged)
        self.instrument.signal.new_ts_data.connect(self.on_new_ts_data)
        if self.instrument.signal.alarm is not None:
            self.instrument.signal.alarm.connect(self.on_data_timeout)
        if self.instrument.signal.alarm_custom is not None:
            self.instrument.signal.alarm_custom.connect(self.on_custom_alarm)
        # Set Widgets
        available_widgets = ((AuxDataWidget, False),
                             (FlowControlWidget, True),
                             (HyperNavCalWidget, True),
                             (MetadataWidget, True),
                             (PumpControlWidget, True),
                             (SelectChannelWidget, False))
        primary_vertical_spacer, secondary_vertical_spacer = True, True
        for widget, secondary_dock in available_widgets:
            if getattr(self.instrument, f'widget_{widget.__snake_name__[:-7]}_enabled') or\
                    widget.__name__ in self.instrument.widgets_to_load:
                self.add_widget(widget, secondary_dock)
                if widget.expanding:
                    if secondary_dock:
                        secondary_vertical_spacer = False
                    else:
                        primary_vertical_spacer = False
        # Add vertical spacer to docks
        if primary_vertical_spacer:
            self.docked_widget_primary_layout.addItem(
                QtGui.QSpacerItem(20, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.MinimumExpanding)
            )
        if secondary_vertical_spacer:
            self.docked_widget_secondary_layout.addItem(
                QtGui.QSpacerItem(20, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.MinimumExpanding)
            )
        # Set secondary dock
        self.toggle_secondary_dock(init=True)
        # Set Central Widget with Plot(s)
        if self.instrument.spectrum_plot_enabled:
            if self.spectrum_plot_widget is None:
                self.spectrum_plot_widget = self.create_spectrum_plot_widget(**self.instrument.spectrum_plot_axis_labels)
            self.centralwidget.layout().addWidget(self.spectrum_plot_widget)
            self.set_spectrum_plot_widget()
            self.instrument.signal.new_spectrum_data.connect(self.on_new_spectrum_data)
        self.timeseries_plot_widget = self.create_timeseries_plot_widget()
        self.centralwidget.layout().addWidget(self.timeseries_plot_widget)
        # Run status update
        #   didn't run with instrument.setup because signal was not connected
        #   need to be after widget(s) initialization
        self.on_status_update()

    @staticmethod
    def create_timeseries_plot_widget():
        widget = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(utcOffset=0)}, enableMenu=False)
        widget.plotItem.setLabel('bottom', 'Time ', units='UTC')
        widget.plotItem.getAxis('bottom').enableAutoSIPrefix(False)
        widget.plotItem.setLabel('left', 'Signal')
        widget.plotItem.getAxis('left').enableAutoSIPrefix(False)
        # widget.plotItem.setLimits(minYRange=0, maxYRange=4500)  # In version 0.9.9
        widget.plotItem.setMouseEnabled(x=False, y=True)
        widget.plotItem.showGrid(x=False, y=True)
        widget.plotItem.enableAutoRange(x=True, y=True)
        widget.plotItem.addLegend()
        return widget

    @staticmethod
    def create_spectrum_plot_widget(x_label_name='Wavelength', x_label_units='nm',
                                    y_label_name='Signal', y_label_units=''):
        widget = pg.PlotWidget(enableMenu=True)
        widget.plotItem.setLabel('bottom', x_label_name, units=x_label_units)
        widget.plotItem.getAxis('bottom').enableAutoSIPrefix(False)
        widget.plotItem.setLabel('left', y_label_name, units=y_label_units)
        widget.plotItem.getAxis('left').enableAutoSIPrefix(False)
        widget.plotItem.setMouseEnabled(x=True, y=True)
        widget.plotItem.showGrid(x=True, y=True)
        widget.plotItem.enableAutoRange(x=True, y=True)
        widget.plotItem.addLegend()
        return widget

    def set_spectrum_plot_widget(self):
        self.spectrum_plot_widget.clear()  # Remove all items (past frame headers)
        min_x, max_x = None, None
        for i, (name, x) in enumerate(zip(self.instrument.spectrum_plot_trace_names,
                                          self.instrument.spectrum_plot_x_values)):
                min_x = min(min_x, min(x)) if min_x is not None else (min(x) if len(x) > 0 else 0)
                max_x = max(max_x, max(x)) if max_x is not None else (max(x) if len(x) > 0 else 10)
                self.spectrum_plot_widget.addItem(pg.PlotCurveItem(
                    pen=pg.mkPen(color=COLOR_SET[i % len(COLOR_SET)], width=2), name=name))
        min_x = 0 if min_x is None else min_x
        max_x = 1 if max_x is None else max_x
        self.spectrum_plot_widget.setXRange(min_x, max_x)
        if hasattr(self.instrument, 'spectrum_plot_x_label'):
            x_label_name, x_label_units = self.instrument.spectrum_plot_x_label
            self.spectrum_plot_widget.plotItem.setLabel('bottom', x_label_name, units=x_label_units)
        if hasattr(self.instrument, 'spectrum_plot_y_label'):
            y_label_name, y_label_units = self.instrument.spectrum_plot_y_label
            self.spectrum_plot_widget.plotItem.setLabel('left', y_label_name, units=y_label_units)
        self.spectrum_plot_widget.setLimits(minXRange=min_x, maxXRange=max_x)

    def set_clock(self):
        zulu = gmtime(time())
        self.label_clock.setText(strftime('%H:%M:%S', zulu) + ' UTC')
        # self.label_date.setText(strftime('%Y/%m/%d', zulu))

    def act_instrument_setup(self):
        logger.debug('Setup instrument')
        setup_dialog = DialogInstrumentUpdate(self.instrument.uuid, self)
        setup_dialog.show()
        if setup_dialog.exec_():
            self.instrument.setup(setup_dialog.cfg)
            self.label_instrument_name.setText(self.instrument.short_name)
            # Set Interface Name
            if self.instrument.interface_name.startswith('com'):
                self.label_open_port.setText('Serial Port')
            elif self.instrument.interface_name.startswith('socket'):
                self.label_open_port.setText('Socket')
            elif self.instrument.interface_name.startswith('usb'):
                self.label_open_port.setText('USB Port')
            # Reset Plots
            self.reset_ts_trace = True  # Force update of variable names in timeseries
            if self.instrument.spectrum_plot_enabled:
                self.set_spectrum_plot_widget()
            # Reset Widgets
            for widget in self.widgets:
                widget.reset()
            self.toggle_secondary_dock()

    def act_instrument_interface(self):
        def error_dialog():
            logger.warning(e)
            QtGui.QMessageBox.warning(self, "Inlinino: Connect " + self.instrument.name,
                                      'ERROR: Failed connecting ' + self.instrument.name + '. ' +
                                      str(e),
                                      QtGui.QMessageBox.Ok)
        if self.instrument.alive:
            logger.debug('Disconnect instrument')
            self.instrument.close()
        else:
            if issubclass(type(self.instrument._interface), SerialInterface):
                dialog = DialogSerialConnection(self)
                dialog.show()
                if dialog.exec_():
                    try:
                        self.instrument.open(port=dialog.port, baudrate=dialog.baudrate, bytesize=dialog.bytesize,
                                             parity=dialog.parity, stopbits=dialog.stopbits, timeout=dialog.timeout)
                        # Save connection parameters for next time
                        CFG.read()
                        CFG.interfaces.setdefault(self.instrument.uuid, {})
                        for k in ('port', 'baudrate', 'bytesize', 'parity', 'stopbits', 'timeout'):
                            CFG.interfaces[self.instrument.uuid][k] = getattr(dialog, k)
                        CFG.write()
                    except IOError as e:
                        error_dialog()
            elif issubclass(type(self.instrument._interface), SocketInterface):
                dialog = DialogSocketConnection(self)
                dialog.show()
                if dialog.exec_():
                    try:
                        self.instrument.open(ip=dialog.ip, port=dialog.port)
                        # Save connection parameters for next time
                        CFG.read()
                        CFG.interfaces.setdefault(self.instrument.uuid, {})
                        for k in ('ip', 'port'):
                            CFG.interfaces[self.instrument.uuid]['socket_' + k] = getattr(dialog, k)
                        CFG.write()
                    except IOError as e:
                        error_dialog()
            elif issubclass(type(self.instrument._interface), USBInterface) or \
                    issubclass(type(self.instrument._interface), USBHIDInterface) or \
                    issubclass(type(self.instrument._interface), USBADUHIDInterface):
                # No need for dialog as automatic
                try:
                    self.instrument.open()
                except IOError as e:
                    error_dialog()
            else:
                logger.error('Interface not supported by GUI.')
                return

    def act_instrument_log(self):
        if self.instrument.log_active:
            logger.debug('Stop logging')
            self.instrument.log_stop()
        else:
            dialog = DialogLoggerOptions(self)
            dialog.show()
            if dialog.exec_():
                self.instrument.log_update_cfg({'filename_prefix': dialog.cover_log_prefix +
                                                                   self.instrument.bare_log_prefix,
                                                'path': dialog.log_path})
                logger.debug('Start logging')
                self.instrument.log_start()

    def act_clear(self):
        if len(self._buffer_data) > 0:
            # Send no data which reset buffers
            self.instrument.signal.new_ts_data.emit([], time())
        if self.instrument.spectrum_plot_enabled:
            self.set_spectrum_plot_widget()
        for widget in self.widgets:
            widget.clear()

    @QtCore.pyqtSlot()
    def on_status_update(self):
        if self.instrument.alive:
            self.button_serial.setText('Close')
            self.button_serial.setToolTip('Disconnect instrument.')
            self.button_log.setEnabled(True)
            if self.instrument.log_active:
                status = 'Logging'
                if self.instrument.log_raw_enabled:
                    if self.instrument.log_prod_enabled:
                        status += ' (raw & prod)'
                    else:
                        status += ' (raw)'
                else:
                    status += ' (prod)'
                self.label_status.setText(status)
                self.label_instrument_name.setStyleSheet('font: 24pt;\ncolor: #12ab29;')
                # Green: #12ab29 (darker) #29ce42 (lighter) #9ce22e (pyQtGraph)
                self.button_log.setText('Stop')
                self.button_log.setToolTip('Stop logging data')
            else:
                self.label_status.setText('Connected')
                self.setWindowTitle(f'Inlinino: {self.instrument.name} [{self.instrument.interface_name}]')
                self.label_instrument_name.setStyleSheet('font: 24pt;\ncolor: #ff9e17;')
                # Orange: #ff9e17 (darker) #ffc12f (lighter)
                self.button_log.setText('Start')
                self.button_log.setToolTip('Start logging data')
        else:
            self.label_status.setText('Disconnected')
            self.setWindowTitle(f'Inlinino: {self.instrument.name}')
            self.label_instrument_name.setStyleSheet('font: 24pt;\ncolor: #e0463e;')
            # Red: #e0463e (darker) #5cd9ef (lighter)  #f92670 (pyQtGraph)
            self.button_serial.setText('Open')
            self.button_serial.setToolTip('Connect instrument.')
            self.button_log.setEnabled(False)
        self.le_filename.setText(self.instrument.log_filename)
        self.le_directory.setText(self.instrument.log_path)
        self.packets_received = 0
        self.label_packets_received.setText(str(self.packets_received))
        self.packets_logged = 0
        self.label_packets_logged.setText(str(self.packets_logged))
        self.packets_corrupted = 0
        self.label_packets_corrupted.setText(str(self.packets_corrupted))
        for widget in self.widgets:
            widget.counter_reset()

    @QtCore.pyqtSlot()
    def on_packet_received(self):
        self.packets_received += 1
        self.label_packets_received.setText(str(self.packets_received))
        if self.packets_corrupted_flag and time() - self.last_packet_corrupted_timestamp > 5:
            self.label_packets_corrupted.setStyleSheet(f'font-weight:normal;color: {self.FOREGROUND_COLOR};')
            self.packets_corrupted_flag = False

    @QtCore.pyqtSlot()
    def on_packet_logged(self):
        self.packets_logged += 1
        if self.packets_received < self.packets_logged < 2:  # Fix inconsistency when start logging
            self.packets_received = self.packets_logged
            self.label_packets_received.setText(str(self.packets_received))
        self.label_packets_logged.setText(str(self.packets_logged))

    @QtCore.pyqtSlot()
    def on_packet_corrupted(self):
        ts = time()
        self.packets_corrupted += 1
        self.label_packets_corrupted.setText(str(self.packets_corrupted))
        if ts - self.last_packet_corrupted_timestamp < 5:  # seconds
            self.label_packets_corrupted.setStyleSheet('font-weight:bold;color: #e0463e;')  # red
            self.packets_corrupted_flag = True
        self.last_packet_corrupted_timestamp = ts

    @QtCore.pyqtSlot(list, float)
    @QtCore.pyqtSlot(np.ndarray, float)
    def on_new_ts_data(self, data, timestamp):
        if len(self._buffer_data) != len(data) or self.reset_ts_trace:
            self.reset_ts_trace = False
            # Init buffers
            self._buffer_timestamp = RingBuffer(self.BUFFER_LENGTH)
            self._buffer_data = [RingBuffer(self.BUFFER_LENGTH) for i in range(len(data))]
            # Re-initialize Plot (need to do so when number of curve changes)
            # TODO FIX HERE for multiple plots
            self.timeseries_plot_widget.clear()
            # new_plot_widget = self.create_timeseries_plot_widget()
            # self.centralwidget.layout().replaceWidget(self.timeseries_plot_widget, new_plot_widget)
            # self.timeseries_plot_widget = new_plot_widget
            # Init curves
            if hasattr(self.instrument, 'widget_active_timeseries_variables_selected'):
                legend = self.instrument.widget_active_timeseries_variables_selected
            else:
                legend = [f"{name} ({units})" for name, units in
                          zip(self.instrument.variable_names, self.instrument.variable_units)]
            for i in range(len(data)):
                self.timeseries_plot_widget.plotItem.addItem(
                    pg.PlotCurveItem(pen=pg.mkPen(color=self.PEN_COLORS[i % len(self.PEN_COLORS)], width=2),
                                     name=legend[i])
                )
        # Update buffers
        self._buffer_timestamp.extend(timestamp)
        for i in range(len(data)):
            self._buffer_data[i].extend(data[i])
        # Update timeseries figure
        if time() - self.last_timeseries_plot_refresh < 1 / self.MAX_PLOT_REFRESH_RATE:
            return
        timestamp = self._buffer_timestamp.get(self.BUFFER_LENGTH)  # Not used anymore
        for i in range(len(data)):
            y = self._buffer_data[i].get(self.BUFFER_LENGTH)
            x = np.arange(len(y))
            y[np.isinf(y)] = 0
            nsel = np.isnan(y)
            if not np.all(nsel):
                sel = np.logical_not(nsel)
                y[nsel] = np.interp(x[nsel], x[sel], y[sel])
                # self.timeseries_widget.plotItem.items[i].setData(y, connect="finite")
                self.timeseries_plot_widget.plotItem.items[i].setData(timestamp[sel], y[sel], connect="finite")
        self.timeseries_plot_widget.plotItem.enableAutoRange(x=True)  # Needed as somehow the user disable sometimes
        self.last_timeseries_plot_refresh = time()

    @QtCore.pyqtSlot(list)
    def on_new_spectrum_data(self, data):
        if time() - self.last_spectrum_plot_refresh < 1 / self.MAX_PLOT_REFRESH_RATE:
            return
        for i, y in enumerate(data):
            if y is None or i > len(self.instrument.spectrum_plot_x_values):
                continue
            x = self.instrument.spectrum_plot_x_values[i]
            # Replace NaN and Inf by interpolated values
            nsel = np.logical_or(np.isinf(y), np.isnan(y))
            sel = np.logical_not(nsel)
            y[nsel] = np.interp(x[nsel], x[sel], y[sel])
            # TODO Check with real instrument if really need trick above
            self.spectrum_plot_widget.plotItem.items[i].setData(x, y, connect="finite")
        self.last_spectrum_plot_refresh = time()

    @QtCore.pyqtSlot(bool)
    def on_data_timeout(self, active):
        if active and not self.alarm_message_box.active:
            txt = self.alarm_message_box.TEXT
            if self.instrument.name is not None:
                txt += f"Instument: {self.instrument.name}\n"
            if self.instrument.interface_name is not None:
                txt += f"Port: {self.instrument.interface_name}\n\n"
            self.alarm_message_box.show(txt)
        elif not active and self.alarm_message_box.active:
            self.alarm_message_box.hide()

    @QtCore.pyqtSlot(str, str)
    def on_custom_alarm(self, text, info_text):
        if not self.alarm_message_box.active:
            self.alarm_message_box.show(text, info_text, sound=False)

    def closeEvent(self, event):
        icon, txt = QtGui.QMessageBox.Question, "Are you sure you want to exit?"
        if self.instrument.widget_hypernav_cal_enabled:
            sbs_txt = self.instrument.check_sbs_sn()
            if sbs_txt:
                icon, txt = QtGui.QMessageBox.Warning, txt + "\nDo you want to exit anyway?"
        msg = QtGui.QMessageBox(icon, "Inlinino: Closing Application", txt,
                                QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, self)
        msg.setWindowModality(QtCore.Qt.WindowModal)
        if msg.exec_() == QtGui.QMessageBox.Yes:
            QtGui.QApplication.instance().closeAllWindows()  # NEEDED IF OTHER WINDOWS OPEN BY SPECIFIC INSTRUMENTS
            event.accept()
        else:
            event.ignore()


class MessageBoxAlarm(QtWidgets.QMessageBox):
    TEXT = "An error occurred with the connection or " \
           "no data was received in the past minute.\n"
    INFO_TEXT = "  + Is the instrument powered?\n" \
                "  + Is the communication cable (e.g. serial, usb, ethernet) connected?\n" \
                "  + Is the instruments configured properly (e.g. automatically send data)?\n"

    def __init__(self, parent):
        super().__init__(QtWidgets.QMessageBox.Warning, "Inlinino: Data Timeout Alarm",
                         self.TEXT, QtWidgets.QMessageBox.Ignore, parent)
        self.setInformativeText(self.INFO_TEXT)
        self.setWindowModality(QtCore.Qt.WindowModal)
        self.active = False
        self.buttonClicked.connect(self.ignore)

        # Setup Sound
        self.alarm_sound = QtMultimedia.QMediaPlayer()
        self.alarm_playlist = QtMultimedia.QMediaPlaylist(self.alarm_sound)
        for file in sorted(glob.glob(os.path.join(PATH_TO_RESOURCES, 'alarm*.wav'))):
            self.alarm_playlist.addMedia(QtMultimedia.QMediaContent(QtCore.QUrl.fromLocalFile(file)))
        if self.alarm_playlist.mediaCount() < 1:
            logger.warning('No alarm sounds available: disabled alarm')
        self.alarm_playlist.setPlaybackMode(QtMultimedia.QMediaPlaylist.Loop)  # Playlist is needed for infinite loop
        self.alarm_sound.setPlaylist(self.alarm_playlist)

    def show(self, txt: str = None, info_txt: str = None, sound: bool = True):
        if not self.active:
            self.setText(self.TEXT if txt is None else txt)
            self.setInformativeText(self.INFO_TEXT if info_txt is None else info_txt)
            super().show()
            if sound:
                self.alarm_playlist.setCurrentIndex(0)
                self.alarm_sound.play()
            self.active = True

    def hide(self):
        if self.active:
            self.alarm_sound.stop()
            super().hide()
            self.active = False

    def ignore(self):
        logger.info('Ignored alarm')
        self.hide()


class DialogStartUp(QtGui.QDialog):
    LOAD_INSTRUMENT = 1
    SETUP_INSTRUMENT = 2

    def __init__(self):
        super(DialogStartUp, self).__init__()
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, 'startup.ui'), self)
        instruments_configured = [i["manufacturer"] + ' ' + i["model"] + ' ' + i["serial_number"]
                                  for i in CFG.instruments.values()]
        self.instrument_uuids = [k for k in CFG.instruments.keys()]
        # self.instruments_to_setup = [i[6:-3] for i in sorted(os.listdir(PATH_TO_RESOURCES)) if i[-3:] == '.ui' and i[:6] == 'setup_']
        self.instruments_to_setup = [os.path.basename(i)[6:-3] for i in sorted(glob.glob(os.path.join(PATH_TO_RESOURCES, 'setup_*.ui')))]
        self.combo_box_instrument_to_load.addItems(instruments_configured)
        self.combo_box_instrument_to_setup.addItems(self.instruments_to_setup)
        self.combo_box_instrument_to_delete.addItems(instruments_configured)
        self.button_load.clicked.connect(self.act_load_instrument)
        self.button_setup.clicked.connect(self.act_setup_instrument)
        self.button_delete.clicked.connect(self.act_delete_instrument)
        self.selected_uuid, self.selected_template = None, None

    def act_load_instrument(self):
        self.selected_uuid = self.instrument_uuids[self.combo_box_instrument_to_load.currentIndex()]
        self.done(self.LOAD_INSTRUMENT)

    def act_setup_instrument(self):
        self.selected_template = self.instruments_to_setup[self.combo_box_instrument_to_setup.currentIndex()]
        self.done(self.SETUP_INSTRUMENT)

    def act_delete_instrument(self):
        index = self.combo_box_instrument_to_delete.currentIndex()
        uuid = self.instrument_uuids[index]
        instrument = self.combo_box_instrument_to_delete.currentText()
        msg = QtGui.QMessageBox(QtWidgets.QMessageBox.Warning, f"Inlinino: Delete {instrument}",
                                f"Are you sure to delete instrument: {instrument} ?",
                                QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, self)
        msg.setWindowModality(QtCore.Qt.WindowModal)
        if msg.exec_() == QtGui.QMessageBox.Yes:
            CFG.read()
            if uuid not in CFG.instruments.keys():
                txt = f"Failed to delete instrument [{uuid}] {instrument}, " \
                      f"configuration was updated by another instance of Inlinino."
                logger.warning(txt)
                QtGui.QMessageBox.warning(self, "Inlinino: Configuration Error", txt, QtGui.QMessageBox.Ok)
                return
            del CFG.instruments[uuid]
            CFG.write()
            self.combo_box_instrument_to_load.removeItem(index)
            self.combo_box_instrument_to_delete.removeItem(index)
            del self.instrument_uuids[index]
            logger.warning(f"Deleted instrument [{uuid}] {instrument}")


class DialogInstrumentSetup(QtGui.QDialog):
    ENCODING = 'ascii'
    OPTIONAL_FIELDS = ['Variable Precision', 'Prefix Custom']
    ADU100_AN01_GAIN2RANGE = {0: '2.5V', 1: '1.25V', 2: '0.625V', 3: '0.312V', 4: '0.156V', 5: '78.12mV', 6: '39.06mV',
                              7: '19.53mV'}  # Values are truncated
    ADU100_AN2_GAIN2RANGE = {1: '10V', 2: '5V'}

    def __init__(self, parent=None):
        super().__init__(parent)

    def connect_backend(self):
        # Connect buttons
        if 'button_browse_log_directory' in self.__dict__.keys():
            self.button_browse_log_directory.clicked.connect(self.act_browse_log_directory)
        if 'button_browse_device_file' in self.__dict__.keys():
            self.button_browse_device_file.clicked.connect(self.act_browse_device_file)
        if 'button_browse_calibration_file' in self.__dict__.keys():
            self.button_browse_calibration_file.clicked.connect(self.act_browse_calibration_file)
        if 'button_browse_tdf_files' in self.__dict__.keys():
            self.button_browse_tdf_files.clicked.connect(self.act_browse_tdf_files)
        if 'button_browse_ini_file' in self.__dict__.keys():
            self.button_browse_ini_file.clicked.connect(self.act_browse_ini_file)
        if 'button_browse_dcal_file' in self.__dict__.keys():
            self.button_browse_dcal_file.clicked.connect(self.act_browse_dcal_file)
        if 'button_browse_zsc_file' in self.__dict__.keys():
            self.button_browse_zsc_file.clicked.connect(self.act_browse_zsc_file)
        if 'button_browse_plaque_file' in self.__dict__.keys():
            self.button_browse_plaque_file.clicked.connect(self.act_browse_plaque_file)
        if 'button_browse_temperature_file' in self.__dict__.keys():
            self.button_browse_temperature_file.clicked.connect(self.act_browse_temperature_file)
        if 'button_browse_px_reg_prt' in self.__dict__.keys():
            self.button_browse_px_reg_prt.clicked.connect(self.act_browse_px_reg_prt)
        if 'button_browse_px_reg_sbd' in self.__dict__.keys():
            self.button_browse_px_reg_sbd.clicked.connect(self.act_browse_px_reg_sbd)
        if 'spinbox_analog_channel0_gain' in self.__dict__.keys():
            self.spinbox_analog_channel0_gain.valueChanged.connect(self.act_update_analog_channel0_input_range)
        if 'spinbox_analog_channel1_gain' in self.__dict__.keys():
            self.spinbox_analog_channel1_gain.valueChanged.connect(self.act_update_analog_channel1_input_range)
        if 'spinbox_analog_channel2_gain' in self.__dict__.keys():
            self.spinbox_analog_channel2_gain.valueChanged.connect(self.act_update_analog_channel2_input_range)
        if 'combobox_model' in self.__dict__.keys():
            self.combobox_model.currentIndexChanged.connect(self.act_activate_fields_for_adu_model)

        # Cannot use default save button as does not provide mean to correctly validate user input
        self.button_save = QtGui.QPushButton('Save')
        self.button_save.setDefault(True)
        self.button_save.clicked.connect(self.act_save)
        self.button_box.addButton(self.button_save, QtGui.QDialogButtonBox.ActionRole)
        self.button_box.rejected.connect(self.reject)

    def act_browse_log_directory(self):
        self.le_log_path.setText(QtGui.QFileDialog.getExistingDirectory(caption='Choose logging directory'))

    def act_browse_device_file(self):
        file_name, selected_filter = QtGui.QFileDialog.getOpenFileName(
            caption='Choose device file', filter='Device File (*.dev *.txt)')
        self.le_device_file.setText(file_name)

    def act_browse_calibration_file(self):  # Specific to Suna and HydroScat
        file_name, selected_filter = QtGui.QFileDialog.getOpenFileName(
            caption='Choose calibration file', filter='Calibration File (*.cal *.CAL)')
        self.le_calibration_file.setText(file_name)

    def act_browse_tdf_files(self):  # sip, cal, or tdf
        file_names, selected_filter = QtGui.QFileDialog.getOpenFileNames(
            caption='Choose calibration file', filter='Calibration File (*.cal *.CAL *.tdf *.TDF *.sip)')
        # Check if sip file
        is_sip = False
        for f in file_names:
            if os.path.splitext(f)[1].lower() == '.sip':
                is_sip = True
                break
        if len(file_names) > 1 and is_sip:
            self.notification('Accept one .sip file OR multiple .cal and .tdf files.')
            return
        # Empty current files for immersed selection
        for i in reversed(range(self.scroll_area_layout_immersed.count())):
            item = self.scroll_area_layout_immersed.itemAt(i)
            if type(item) == QtGui.QWidgetItem:
                item.widget().setParent(None)
            elif type(item) == QtGui.QLayoutItem:
                item.layout().setParent(None)
        # Update selection of immersed files
        if is_sip:
            self.tdf_files = file_names[0]
            file_names = [f for f in zipfile.ZipFile(self.tdf_files, 'r').namelist()
                          if os.path.splitext(f)[1].lower() in pySat.Parser.VALID_CAL_EXTENSIONS
                          and os.path.basename(f)[0] != '.']
        else:
            self.tdf_files = file_names
        for f in file_names:
            self.scroll_area_layout_immersed.addWidget(QtWidgets.QCheckBox(os.path.basename(f)))
        self.scroll_area_layout_immersed.addItem(
            QtGui.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding))

    def act_browse_ini_file(self):
        file_name, selected_filter = QtGui.QFileDialog.getOpenFileName(
            caption='Choose initialization file', filter='Ini File (*.ini)')
        self.le_ini_file.setText(file_name)

    def act_browse_dcal_file(self):
        file_name, selected_filter = QtGui.QFileDialog.getOpenFileName(
            caption='Choose DCAL file', filter='DCAL File (*.asc)')
        self.le_dcal_file.setText(file_name)

    def act_browse_zsc_file(self):
        file_name, selected_filter = QtGui.QFileDialog.getOpenFileName(
            caption='Choose ZSC file', filter='ZSC File (*.asc)')
        self.le_zsc_file.setText(file_name)

    def act_browse_plaque_file(self):
        file_name, selected_filter = QtGui.QFileDialog.getOpenFileName(
            caption='Choose plaque calibration file', filter='Plaque File (*.mat)')
        self.le_plaque_file.setText(file_name)

    def act_browse_temperature_file(self):
        file_name, selected_filter = QtGui.QFileDialog.getOpenFileName(
            caption='Choose temperature calibration file', filter='Temperature File (*.mat)')
        self.le_temperature_file.setText(file_name)

    def act_browse_px_reg_prt(self):
        file_name, selected_filter = QtGui.QFileDialog.getOpenFileName(
            caption='Choose port side pixel registration file',
            filter='Registration File (*.cgs *.cal *.tdf *.CGS *.CAL *.TDF)')
        self.le_optional_px_reg_path_prt.setText(file_name)

    def act_browse_px_reg_sbd(self):
        file_name, selected_filter = QtGui.QFileDialog.getOpenFileName(
            caption='Choose starboard pixel registration file',
            filter='Registration File (*.cgs *.cal *.tdf *.CGS *.CAL *.TDF)')
        self.le_optional_px_reg_path_sbd.setText(file_name)

    def act_update_analog_channel0_input_range(self):
        self.label_analog_channel0_input_range.setText(
            f'0 - {self.ADU100_AN01_GAIN2RANGE[self.spinbox_analog_channel0_gain.value()]}')

    def act_update_analog_channel1_input_range(self):
        self.label_analog_channel1_input_range.setText(
            f'0 - {self.ADU100_AN01_GAIN2RANGE[self.spinbox_analog_channel1_gain.value()]}')

    def act_update_analog_channel2_input_range(self):
        self.label_analog_channel2_input_range.setText(
            f'0 - {self.ADU100_AN2_GAIN2RANGE[self.spinbox_analog_channel2_gain.value()]}')

    def act_activate_fields_for_adu_model(self):
        model = self.combobox_model.currentText()
        if model == 'ADU100':
            self.group_box_analog.setEnabled(True)
        elif model in ('ADU200', 'ADU208'):
            self.group_box_analog.setEnabled(False)
        else:
            raise ValueError(f'Model {model} not supported.')

    def act_save(self):
        # Read form
        fields = [a for a in self.__dict__.keys() if 'combobox_' in a or a.startswith('te_') or
                  a.startswith('le_') or a.startswith('sb_') or a.startswith('dsb_') or a.startswith('cb_')]
        empty_fields = list()
        for f in fields:
            field_prefix, field_name = f.split('_', 1)
            field_optional = 'optional' in f
            if field_optional:
                field_name = field_name[9:]
            field_pretty_name = field_name.replace('_', ' ').title()
            if f in ['combobox_interface', 'combobox_model', *[f'combobox_relay{i}_mode' for i in range(4)]]:
                self.cfg[field_name] = self.__dict__[f].currentText()
            elif field_prefix in ['le', 'sb', 'dsb']:
                value = getattr(self, f).text().strip()
                if not field_optional and not value:
                    empty_fields.append(field_pretty_name)
                    continue
                # Apply special formatting to specific variables
                try:
                    if 'variable_' in field_name:
                        value = [v.strip() for v in value.split(',')]
                        if 'variable_columns' in field_name:
                            value = [int(x) for x in value]
                    elif field_name in ['terminator', 'separator']:
                        # if len(value) > 3 and (value[:1] == "b'" and value[-1] == "'"):
                        #     value = bytes(value[2:-1], 'ascii')
                        value = value.strip().encode(self.ENCODING).decode('unicode_escape').encode(self.ENCODING)
                    elif field_prefix == 'sb':  # SpinBox
                        # a spinbox will contain either an int or float
                        try:
                            value = int(value)
                        except ValueError:
                            value = float(value)
                    elif field_prefix == 'dsb':  # DoubleSpinBox
                        value = float(value)
                    else:
                        value.strip()
                except:
                    self.notification('Unable to parse special variable: ' + field_pretty_name, sys.exc_info()[0])
                    return
                self.cfg[field_name] = value
            elif field_prefix == 'te':
                value = getattr(self, f).toPlainText().strip()
                if not value:
                    empty_fields.append(field_pretty_name)
                    continue
                try:
                    value = [v.strip() for v in value.split(',')]
                except:
                    self.notification('Unable to parse special variable: ' + field_pretty_name, sys.exc_info()[0])
                    return
                self.cfg[field_name] = value
            elif field_prefix == 'combobox':
                if getattr(self, f).currentText() == 'on':
                    self.cfg[field_name] = True
                else:
                    self.cfg[field_name] = False
            elif field_prefix == 'cb':
                self.cfg[field_name] = getattr(self, f).isChecked()
        if self.cfg['module'] == 'dataq':
            # Remove optional fields specific to dataq
            f2rm = [f for f in empty_fields if f.startswith('Variable')]
            for f in f2rm:
                del empty_fields[empty_fields.index(f)]
        for f in self.OPTIONAL_FIELDS:
            try:
                empty_fields.pop(empty_fields.index(f))
            except ValueError:
                pass
        if hasattr(self, 'tdf_files'):
            if len(self.tdf_files) == 0:
                empty_fields.append('Calibration or Telemetry Definition File(s)')
        if hasattr(self, 'scroll_area_layout_immersed'):
            if self.scroll_area_layout_immersed.count() == 0:
                empty_fields.append('Empty .sip file.')
        if empty_fields:
            self.notification('Fill required fields.', '\n'.join(empty_fields))
            return
        # Check fields specific to modules
        if self.cfg['module'] == 'generic':
            if not self.check_variables_pass():
                return
            if not self.cfg['log_raw'] and not self.cfg['log_products']:
                self.notification('Invalid logger configuration. '
                                  'At least one logger must be ON (to either log raw or parsed data).')
                return
        elif self.cfg['module'] == 'acs':
            self.cfg['manufacturer'] = 'WetLabs'
            try:
                # serial number in ACSParser is given in hexadecimal and preceded by 2 bytes indicating meter type
                foo = ACSParser(self.cfg['device_file']).serial_number
                if foo[:4] == '0x53':
                    self.cfg['model'] = 'ACS'
                else:
                    self.cfg['model'] = 'UnknownMeterType'
                self.cfg['serial_number'] = str(int(foo[-6:], 16))
            except Exception as e:
                logger.error(e)
                self.notification('Unable to parse acs device file.')
                return
            if 'log_raw' not in self.cfg.keys():
                self.cfg['log_raw'] = True
            if 'log_products' not in self.cfg.keys():
                self.cfg['log_products'] = True
        elif self.cfg['module'] == 'lisst':
            self.cfg['manufacturer'] = 'Sequoia'
            self.cfg['model'] = 'LISST'
            try:
                self.cfg['serial_number'] = str(LISSTParser(self.cfg['device_file'], self.cfg['ini_file'],
                                                            self.cfg['dcal_file'], self.cfg['zsc_file']).serial_number)
            except:
                self.notification('Unable to parse lisst device, ini, dcal, or zsc file.')
                return
            if 'log_raw' not in self.cfg.keys():
                self.cfg['log_raw'] = True
            if 'log_products' not in self.cfg.keys():
                self.cfg['log_products'] = True
        elif self.cfg['module'] == 'ontrak':
            self.cfg['model'] = self.combobox_model.currentText()
            self.cfg['relay0_enabled'] = self.checkbox_relay0_enabled.isChecked()
            self.cfg['event_counter_channels_enabled'], self.cfg['event_counter_k_factors'] = [], []
            for c in range(4):
                if getattr(self, 'checkbox_event_counter_channel%d_enabled' % (c)).isChecked():
                    self.cfg['event_counter_channels_enabled'].append(c)
                    k = getattr(self, 'spinbox_event_counter_channel%d_k_factor' % (c)).value()
                    self.cfg['event_counter_k_factors'].append(k)
            self.cfg['low_flow_alarm_enabled'] = self.checkbox_low_flow_alarm_enabled.isChecked()
            self.cfg['analog_channels_enabled'], self.cfg['analog_channels_gains'] = [], []
            for c in range(3):
                if getattr(self, 'checkbox_analog_channel%d_enabled' % (c)).isChecked():
                    self.cfg['analog_channels_enabled'].append(c)
                    g = getattr(self, 'spinbox_analog_channel%d_gain' % (c)).value()
                    self.cfg['analog_channels_gains'].append(g)
            if not (self.cfg['relay0_enabled'] or self.cfg['event_counter_channels_enabled'] or
                    (self.cfg['model'] == 'ADU100' and self.cfg['analog_channels_enabled'])):
                self.notification('At least one switch, one flowmeter, or one analog channel must be selected.')
                return
            if not (self.cfg['log_raw'] or self.cfg['log_products']):
                self.notification('Warning: no data will be logged.')
        elif self.cfg['module'] == 'dataq':
            self.cfg['channels_enabled'] = []
            for c in range(8):
                if getattr(self, 'checkbox_channel%d_enabled' % (c+1)).isChecked():
                    self.cfg['channels_enabled'].append(c)
            if not self.cfg['channels_enabled']:
                self.notification('At least one channel must be enabled.', 'Nothing to log if no channels are enabled.')
                return
            if not self.check_variables_pass():
                return
            if 'log_raw' not in self.cfg.keys():
                self.cfg['log_raw'] = False
            if 'log_products' not in self.cfg.keys():
                self.cfg['log_products'] = True
        elif self.cfg['module'] in 'satlantic':
            self.cfg['tdf_files'] = self.tdf_files
            self.cfg['immersed'] = []
            for i in range(self.scroll_area_layout_immersed.count()):
                item = self.scroll_area_layout_immersed.itemAt(i)
                if type(item) == QtGui.QWidgetItem:
                    self.cfg['immersed'].append(bool(item.widget().checkState()))
        elif self.cfg['module'] == 'hypernav':
            try:
                self.cfg['prt_sbs_sn'] = int(self.cfg['prt_sbs_sn'])
            except ValueError:
                self.notification('Port side serial number must be an integer.')
                return
            try:
                self.cfg['sbd_sbs_sn'] = int(self.cfg['sbd_sbs_sn'])
            except ValueError:
                self.notification('Starboard serial number must be an integer.')
                return
            try:
                for path in (self.cfg['px_reg_path_prt'], self.cfg['px_reg_path_sbd']):
                    if not path:
                        continue
                    elif os.path.splitext(path)[1] == '.cgs':
                        read_manufacturer_pixel_registration(path)
                    elif os.path.splitext(path)[1] in pySat.Instrument.VALID_CAL_EXTENSIONS:
                        td = pySat.Parser(path)
                        if not td.variable_frame_length:
                            raise ValueError('Inlinino only supports SATY*Z files for hypernav.')
                    else:
                        raise ValueError(f'Invalid file extension, only support '
                                         f'{", ".join(pySat.Instrument.VALID_CAL_EXTENSIONS)}and .cgs.')
            except Exception as e:
                self.notification('Error in HyperNav configuration.', e)
                return
        elif self.cfg['module'] == 'hydroscat':
            try:
                f = configparser.ConfigParser()
                f.read_file(open(self.cfg['calibration_file'], 'r'))
                self.cfg['manufacturer'] = 'HobiLabs'
                self.cfg['model'] = 'HydroScat'
                self.cfg['serial_number'] = f.get('General', 'Serial')
            except configparser.Error as e:
                self.notification("Invalid HydroScat calibration file.", details=str(e))
                return
            except FileNotFoundError:
                self.notification(f"No such calibration file: {self.cfg['calibration_file']}")
                return
        # Update global instrument cfg
        CFG.read()  # Update local cfg if other instance updated cfg
        CFG.instruments[self.cfg_uuid] = self.cfg.copy()
        CFG.write()
        self.accept()

    def check_variables_pass(self):
        variable_keys = [v for v in self.cfg.keys() if 'variable_' in v]
        if variable_keys:
            # Check length
            n = len(self.cfg['variable_names'])
            for k in variable_keys:
                if n != len(self.cfg[k]):
                    self.notification('Inconsistent length. Variable Names, Variable Units, Variable Columns,'
                                      'Variable Types, and Variable Precision must have the same number of elements '
                                      'separated by commas.')
                    return False
            # Check type
            if 'variable_types' in self.cfg:
                for v in self.cfg['variable_types']:
                    if v not in ['int', 'float']:
                        self.notification('Invalid variable type')
                        return False
            # Check precision
            if 'variable_precision' in self.cfg:
                if not (len(self.cfg['variable_precision']) == 1 and self.cfg['variable_precision'][0] == ''):
                    for v in self.cfg['variable_precision']:
                        try:
                            ', '.join(p % d for p, d in zip(self.cfg['variable_precision'],
                                                            range(len(self.cfg['variable_precision']))))
                        except ValueError:
                            self.notification('Invalid variable precision format. '
                                              'Expect type specific formatting (e.g. %d or %.3f) separated by commas.')
                            return False
        return True

    def notification(self, message, details=None):
        msg = QtGui.QMessageBox(QtWidgets.QMessageBox.Warning, "Inlinino: Setup Instrument Warning",
                                message,
                                QtGui.QMessageBox.Ok, self)
        if details:
            msg.setDetailedText(str(details))
        msg.setWindowModality(QtCore.Qt.WindowModal)
        msg.exec_()


class DialogInstrumentCreate(DialogInstrumentSetup):
    def __init__(self, template, parent=None):
        # Init parent
        super().__init__(parent)
        # Load template from instrument type
        self.cfg_uuid = str(uuid.uuid1())
        self.cfg = {'module': template}
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, 'setup_' + template + '.ui'), self)
        # Add specific fields
        if hasattr(self, 'scroll_area_layout_immersed'):
            self.tdf_files = []
        # Connect Buttons
        self.connect_backend()


class DialogInstrumentUpdate(DialogInstrumentSetup):
    def __init__(self, uuid, parent=None):
        # Init parent
        super().__init__(parent)
        # Check if instrument exists
        if uuid not in CFG.instruments.keys():
            logger.warning('Instrument was deleted.')
            QtGui.QMessageBox.warning(self, "Inlinino: Configuration Error",
                                      'ERROR: Instrument was deleted.',
                                      QtGui.QMessageBox.Ok)
            self.cancel()
        # Load from preconfigured instrument
        self.cfg_uuid = uuid
        self.cfg = CFG.instruments[uuid]
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, 'setup_' + self.cfg['module'] + '.ui'), self)
        # Get optional fields
        optional_fields = [k[12:] for k in self.__dict__.keys() if 'optional' in k]
        # Populate fields
        for k, v in self.cfg.items():
            if k in optional_fields:
                k = 'optional_' + k
            if hasattr(self, 'le_' + k):
                if isinstance(v, bytes):
                    getattr(self, 'le_' + k).setText(v.decode().encode('unicode_escape').decode())
                elif isinstance(v, list):
                    getattr(self, 'le_' + k).setText(', '.join([str(vv) for vv in v]))
                elif isinstance(v, int):
                    getattr(self, 'le_' + k).setText(f'{v:d}')
                else:
                    getattr(self, 'le_' + k).setText(v)
            elif hasattr(self, 'te_' + k):
                if isinstance(v, list):
                    getattr(self, 'te_' + k).setPlainText(',\n'.join([str(vv) for vv in v]))
                else:
                    getattr(self, 'te_' + k).setPlainText(v)
            elif hasattr(self, 'combobox_' + k):
                if v:
                    getattr(self, 'combobox_' + k).setCurrentIndex(0)
                else:
                    getattr(self, 'combobox_' + k).setCurrentIndex(1)
            elif hasattr(self, 'dsb_' + k):
                # double spin box
                getattr(self, 'dsb_' + k).setValue(self.cfg[k])
            elif hasattr(self, 'sb_' + k):
                # spin box
                getattr(self, 'sb_' + k).setValue(self.cfg[k])
            elif hasattr(self, 'cb_' + k):
                # check boxes
                getattr(self, 'cb_' + k).setChecked(self.cfg[k])
        # Populate special fields specific to each module
        if self.cfg['module'] == 'dataq':
            for c in self.cfg['channels_enabled']:
                getattr(self, 'checkbox_channel%d_enabled' % (c + 1)).setChecked(True)
            # Handle legacy configuration
            for k in [k for k in self.cfg.keys() if k.startswith('variable_')]:
                if len(self.cfg[k]) == 1 and self.cfg[k][0] == '':
                    del self.cfg[k]
        if self.cfg['module'] == 'ontrak':
            try:
                self.combobox_model.setCurrentIndex([self.combobox_model.itemText(i)
                                                     for i in range(self.combobox_model.count())]
                                                    .index(self.cfg['model']))
            except ValueError:
                logger.warning('Configured model not available in GUI. Interface set to GUI default.')
            self.act_activate_fields_for_adu_model()
            try:
                self.combobox_relay0_mode.setCurrentIndex([self.combobox_relay0_mode.itemText(i)
                                                           for i in range(self.combobox_relay0_mode.count())]
                                                          .index(self.cfg['relay0_mode']))
            except ValueError:
                logger.warning('Configured relay0_mode not available in GUI. Interface set to GUI default.')
            self.checkbox_relay0_enabled.setChecked(self.cfg['relay0_enabled'])
            for c, g in zip(self.cfg['event_counter_channels_enabled'], self.cfg['event_counter_k_factors']):
                getattr(self, 'checkbox_event_counter_channel%d_enabled' % (c)).setChecked(True)
                getattr(self, 'spinbox_event_counter_channel%d_k_factor' % (c)).setValue(g)
            if 'low_flow_alarm_enabled' in self.cfg.keys():
                self.checkbox_low_flow_alarm_enabled.setChecked(self.cfg['low_flow_alarm_enabled'])
            for c, g in zip(self.cfg['analog_channels_enabled'], self.cfg['analog_channels_gains']):
                getattr(self, 'checkbox_analog_channel%d_enabled' % (c)).setChecked(True)
                getattr(self, 'spinbox_analog_channel%d_gain' % (c)).setValue(g)
        if hasattr(self, 'combobox_interface'):
            if 'interface' in self.cfg.keys():
                try:
                    self.combobox_interface.setCurrentIndex([self.combobox_interface.itemText(i)
                                                             for i in range(self.combobox_interface.count())]
                                                            .index(self.cfg['interface']))
                except ValueError:
                    logger.warning('Configured interface not available in GUI. Interface set to GUI default.')
        if hasattr(self, 'scroll_area_layout_immersed'):
            if 'immersed' in self.cfg.keys() and 'tdf_files' in self.cfg.keys():
                self.tdf_files = self.cfg['tdf_files']
                for f, i in zip(self.tdf_files, self.cfg['immersed']):
                    widget = QtWidgets.QCheckBox(os.path.basename(f))
                    if i:
                        widget.setChecked(True)
                    self.scroll_area_layout_immersed.addWidget(widget)
                self.scroll_area_layout_immersed.addItem(
                    QtGui.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding))
            else:
                self.tdf_files = []
        # Connect Buttons
        self.connect_backend()


class DialogSerialConnection(QtGui.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, 'serial_connection.ui'), self)
        instrument = parent.instrument
        # Connect buttons
        self.button_box.button(QtGui.QDialogButtonBox.Open).clicked.connect(self.accept)
        self.button_box.button(QtGui.QDialogButtonBox.Cancel).clicked.connect(self.reject)
        # Update ports list
        self.ports = list_serial_comports()
        # self.ports.append(type('obj', (object,), {'device': '/dev/ttys001', 'product': 'macOS Virtual Serial', 'description': 'n/a'}))  # Debug macOS serial
        ports_device = []
        for p in self.ports:
            # print(f'\n\n===\n{p.description}\n{p.device}\n{p.hwid}\n{p.interface}\n{p.location}\n{p.manufacturer}\n{p.name}\n{p.pid}\n{p.product}\n{p.serial_number}\n{p.vid}')
            p_name = str(p.device)
            if p.description is not None and p.description != 'n/a':
                p_name += ' - ' + str(p.description)
            self.cb_port.addItem(p_name)
            ports_device.append(p.device)
        # Set default values based on instrument
        baudrate, bytesize, parity, stopbits, timeout = '19200', '8 bits', 'none', '1', 2
        if hasattr(instrument, 'default_serial_baudrate'):
            baudrate = str(instrument.default_serial_baudrate)
        if hasattr(instrument, 'default_serial_parity'):
            parity = str(instrument.default_serial_parity)
        if hasattr(instrument, 'default_serial_timeout'):
            timeout = instrument.default_serial_timeout
        if instrument.uuid in CFG.interfaces.keys():
            if isinstance(CFG.interfaces[instrument.uuid], str):  # Support legacy format
                CFG.interfaces[instrument.uuid]['port'] = CFG.interfaces[instrument.uuid]
            if 'port' in CFG.interfaces[instrument.uuid].keys():
                port = CFG.interfaces[instrument.uuid]['port']
                if port in ports_device:
                    self.cb_port.setCurrentIndex(ports_device.index(port))
            if 'baudrate' in CFG.interfaces[instrument.uuid].keys():
                baudrate = str(CFG.interfaces[instrument.uuid]['baudrate'])
            if 'bytesize' in CFG.interfaces[instrument.uuid].keys():
                bytesize = f"{CFG.interfaces[instrument.uuid]['bytesize']} bits"
            if 'parity' in CFG.interfaces[instrument.uuid].keys():
                try:
                    parity = {serial.PARITY_EVEN: 'even', serial.PARITY_ODD: 'odd',
                              serial.PARITY_MARK: 'mark', serial.PARITY_SPACE: 'space',
                              serial.PARITY_NONE: 'none'}[CFG.interfaces[instrument.uuid]['parity']]
                except KeyError:
                    logger.warning('cfg parity invalid.')
            if 'stopbits' in CFG.interfaces[instrument.uuid].keys():
                stopbits = str(CFG.interfaces[instrument.uuid]['stopbits'])
            if 'timeout' in CFG.interfaces[instrument.uuid].keys():
                timeout = CFG.interfaces[instrument.uuid]['timeout']
        self.cb_baudrate.setCurrentIndex([self.cb_baudrate.itemText(i) for i in range(self.cb_baudrate.count())].index(baudrate))
        self.cb_bytesize.setCurrentIndex([self.cb_bytesize.itemText(i) for i in range(self.cb_bytesize.count())].index(bytesize))
        self.cb_parity.setCurrentIndex([self.cb_parity.itemText(i) for i in range(self.cb_parity.count())].index(parity))
        self.cb_stopbits.setCurrentIndex([self.cb_stopbits.itemText(i) for i in range(self.cb_stopbits.count())].index(stopbits))
        self.sb_timeout.setValue(timeout)

    @property
    def port(self) -> str:
        return self.ports[self.cb_port.currentIndex()].device

    @property
    def baudrate(self) -> int:
        return int(self.cb_baudrate.currentText())

    @property
    def bytesize(self) -> int:
        if self.cb_bytesize.currentText() == '5 bits':
            return serial.FIVEBITS
        elif self.cb_bytesize.currentText() == '6 bits':
            return serial.SIXBITS
        elif self.cb_bytesize.currentText() == '7 bits':
            return serial.SEVENBITS
        elif self.cb_bytesize.currentText() == '8 bits':
            return serial.EIGHTBITS
        raise ValueError('serial byte size not defined')

    @property
    def parity(self) -> int:
        if self.cb_parity.currentText() == 'none':
            return serial.PARITY_NONE
        elif self.cb_parity.currentText() == 'even':
            return serial.PARITY_EVEN
        elif self.cb_parity.currentText() == 'odd':
            return serial.PARITY_ODD
        elif self.cb_parity.currentText() == 'mark':
            return serial.PARITY_MARK
        elif self.cb_parity.currentText() == 'space':
            return serial.PARITY_SPACE
        raise ValueError('serial parity not defined')

    @property
    def stopbits(self) -> (int, float):
        if self.cb_stopbits.currentText() == '1':
            return serial.STOPBITS_ONE
        elif self.cb_stopbits.currentText() == '1.5':
            return serial.STOPBITS_ONE_POINT_FIVE
        elif self.cb_stopbits.currentText() == '2':
            return serial.STOPBITS_TWO
        raise ValueError('serial stop bits not defined')

    @property
    def timeout(self) -> float:
        return self.sb_timeout.value()


class DialogSocketConnection(QtGui.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        instrument = parent.instrument
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, 'socket_connection.ui'), self)
        # Set defaults
        if instrument.uuid in CFG.interfaces.keys():
            if isinstance(CFG.interfaces[instrument.uuid], str):  # Support legacy format
                CFG.interfaces[instrument.uuid]['port'] = CFG.interfaces[instrument.uuid]
            if 'socket_ip' in CFG.interfaces[instrument.uuid].keys():
                ip = str(CFG.interfaces[instrument.uuid]['socket_ip'])
                self.le_ip.setText(ip)
            if 'socket_port' in CFG.interfaces[instrument.uuid].keys():
                port = CFG.interfaces[instrument.uuid]['socket_port']
                self.sb_port.setValue(port)
        # Connect buttons
        self.button_box.button(QtGui.QDialogButtonBox.Open).clicked.connect(self.accept)
        self.button_box.button(QtGui.QDialogButtonBox.Cancel).clicked.connect(self.reject)

    @property
    def ip(self) -> str:
        return self.le_ip.text()

    @property
    def port(self) -> int:
        return int(self.sb_port.value())

    # @property
    # def timeout(self) -> int:
    #     return int(self.sb_timeout.value())


class DialogLoggerOptions(QtGui.QDialog):
    def __init__(self, parent):
        super().__init__(parent)  #, QtCore.Qt.WindowStaysOnTopHint
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, 'logger_options.ui'), self)
        self.le_prefix_custom_connected = False
        self.instrument = parent.instrument
        # Logger Options
        self.le_log_path.setText(self.instrument.log_path)
        self.button_browse_log_directory.clicked.connect(self.act_browse_log_directory)
        self.update_filename_template()
        # Connect Prefix Checkbox to update Filename Template
        self.cb_prefix_diw.toggled.connect(self.update_filename_template)
        self.cb_prefix_fsw.toggled.connect(self.update_filename_template)
        self.cb_prefix_dark.toggled.connect(self.update_filename_template)
        self.cb_prefix_custom.toggled.connect(self.update_filename_template)
        # Connect buttons
        self.button_box.button(QtGui.QDialogButtonBox.Save).setDefault(True)
        self.button_box.button(QtGui.QDialogButtonBox.Save).clicked.connect(self.accept)
        self.button_box.button(QtGui.QDialogButtonBox.Cancel).clicked.connect(self.reject)

    @property
    def cover_log_prefix(self) -> str:
        prefix = ''
        if self.cb_prefix_diw.isChecked():
            prefix += 'DIW'
        if self.cb_prefix_fsw.isChecked():
            prefix += 'FSW'
        if self.cb_prefix_dark.isChecked():
            prefix += 'DARK'
        if self.cb_prefix_custom.isChecked():
            if not self.le_prefix_custom_connected:
                self.le_prefix_custom.textChanged.connect(self.update_filename_template)
                self.le_prefix_custom_connected = True
            prefix += self.le_prefix_custom.text()
        elif self.le_prefix_custom_connected:
            self.le_prefix_custom.textChanged.disconnect(self.update_filename_template)
            self.le_prefix_custom_connected = False
        if prefix:
            prefix += '_'
        # Check All required fields are complete
        return prefix

    @property
    def log_path(self) -> str:
        return self.le_log_path.text()

    def act_browse_log_directory(self):
        self.le_log_path.setText(QtGui.QFileDialog.getExistingDirectory(caption='Choose logging directory',
                                                     directory=self.le_log_path.text()))
        self.show()

    def update_filename_template(self):
        # self.le_filename_template.setText(instrument.log_filename)  # Not up to date
        self.le_filename_template.setText(self.cover_log_prefix + self.instrument.bare_log_prefix +
                                          '_YYYYMMDD_hhmmss.' + self.instrument.log_get_file_ext())


class App(QtGui.QApplication):
    def __init__(self, *args):
        QtGui.QApplication.__init__(self, *args)
        self.splash_screen = QtGui.QSplashScreen(QtGui.QPixmap(os.path.join(PATH_TO_RESOURCES, 'inlinino.ico')))
        self.splash_screen.show()
        self.setWindowIcon(QtGui.QIcon(os.path.join(PATH_TO_RESOURCES, 'inlinino.ico')))
        self.main_window = MainWindow()
        self.startup_dialog = DialogStartUp()
        self.splash_screen.close()

    def start(self, instrument_index=None):
        if isinstance(instrument_index, int) and instrument_index < len(CFG.instruments):
            # Get instrument index
            instrument_uuid = list(CFG.instruments.keys())[instrument_index]
        elif isinstance(instrument_index, str) and instrument_index in CFG.instruments.keys():
            instrument_uuid = instrument_index
        else:
            logger.debug('Startup Dialog')
            self.startup_dialog.show()
            act = self.startup_dialog.exec_()
            if act == self.startup_dialog.LOAD_INSTRUMENT:
                instrument_uuid = self.startup_dialog.selected_uuid
            elif act == self.startup_dialog.SETUP_INSTRUMENT:
                setup_dialog = DialogInstrumentCreate(self.startup_dialog.selected_template)
                setup_dialog.show()
                if setup_dialog.exec_():
                    instrument_uuid = setup_dialog.cfg_uuid
                else:
                    logger.info('Setup closed')
                    self.start()  # Restart application to go back to startup screen
            else:
                logger.info('Startup closed')
                sys.exit()

        # Load instrument
        instrument_name = CFG.instruments[instrument_uuid]['model'] + ' ' \
                          + CFG.instruments[instrument_uuid]['serial_number']
        instrument_module_name = CFG.instruments[instrument_uuid]['module']
        logger.debug('Loading instrument [' + str(instrument_uuid) + '] ' + instrument_name)
        instrument_loaded = False
        while not instrument_loaded:
            try:
                instrument_class = {'generic': Instrument, 'acs': ACS, 'apogee': ApogeeQuantumSensor,
                                    'dataq': DATAQ, 'hydroscat': HydroScat, 'hyperbb': HyperBB, 'hypernav': HyperNav,
                                    'lisst': LISST, 'nmea': NMEA,
                                    'ontrak': Ontrak,
                                    'satlantic': Satlantic,
                                    'sunav1': SunaV1, 'sunav2': SunaV2, 'taratsg': TaraTSG}
                instrument_signal = HyperNavSignals if instrument_module_name == 'hypernav' else InstrumentSignals
                if instrument_module_name not in instrument_class.keys():
                    logger.critical('Instrument module not supported')
                    sys.exit(-1)
                self.main_window.init_instrument(instrument_class[instrument_module_name](
                    instrument_uuid, CFG.instruments[instrument_uuid].copy(), instrument_signal()
                ))
                instrument_loaded = True
            except Exception as e:
                raise e
                logger.warning('Unable to load instrument.')
                logger.warning(e)
                self.closeAllWindows()  # ACS, HyperBB, LISST, and Suna are opening pyqtgraph windows
                # Dialog Box
                setup_dialog = DialogInstrumentUpdate(instrument_uuid)
                setup_dialog.show()
                setup_dialog.notification('Unable to load instrument. Please check configuration.', e)
                if setup_dialog.exec_():
                    logger.info('Updated configuration')
                else:
                    logger.info('Setup closed')
                    self.start()  # Restart application to go back to startup screen
        # Start Main Window
        self.main_window.show()
        sys.exit(self.exec_())
