from pyqtgraph.Qt import QtGui, QtCore, QtWidgets, uic
import pyqtgraph as pg
import sys, os
import logging
from time import time, gmtime, strftime
from serial.tools.list_ports import comports as list_serial_comports
from serial import SerialException
from inlinino import RingBuffer, CFG, __version__, PATH_TO_RESOURCES
from inlinino.instruments import Instrument
from inlinino.instruments.acs import ACS
from inlinino.instruments.lisst import LISST
from inlinino.instruments.dataq import DATAQ
from pyACS.acs import ACS as ACSParser
from inlinino.instruments.lisst import LISSTParser
import numpy as np
from math import floor

logger = logging.getLogger('GUI')


class InstrumentSignals(QtCore.QObject):
    status_update = QtCore.pyqtSignal()
    packet_received = QtCore.pyqtSignal()
    packet_corrupted = QtCore.pyqtSignal()
    packet_logged = QtCore.pyqtSignal()
    new_data = QtCore.pyqtSignal(object, float)
    new_aux_data = QtCore.pyqtSignal(list)


def seconds_to_strmmss(seconds):
    min = floor(seconds / 60)
    sec = seconds % 60
    return '%d:%02d' % (min, sec)


class ReverseTimeAxisItem(pg.AxisItem):
    def __init__(self, buffer_length, sample_rate, *args, **kwargs):
        self.buffer_length = buffer_length
        self.sample_rate = sample_rate
        pg.AxisItem.__init__(self, *args, **kwargs)

    def tickStrings(self, values, scale, spacing):
        return [seconds_to_strmmss((self.buffer_length - t) / self.sample_rate) for t in values]


class ReverseAxisItem(pg.AxisItem):
    def __init__(self, buffer_length, *args, **kwargs):
        self.buffer_length = buffer_length
        pg.AxisItem.__init__(self, *args, **kwargs)

    def tickStrings(self, values, scale, spacing):
        return [self.buffer_length - t for t in values]


class MainWindow(QtGui.QMainWindow):
    BACKGROUND_COLOR = '#F8F8F2'
    FOREGROUND_COLOR = '#26292C'
    BUFFER_LENGTH = 240
    MAX_PLOT_REFRESH_RATE = 4   # Hz

    def __init__(self, instrument=None):
        super(MainWindow, self).__init__()
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, 'main.ui'), self)
        # Graphical Adjustments
        self.dock_widget.setTitleBarWidget(QtGui.QWidget(None))
        self.label_app_version.setText('Inlinino v' + __version__)
        # Set Colors
        palette = QtGui.QPalette()
        palette.setColor(palette.Window, QtGui.QColor(self.BACKGROUND_COLOR))  # Background
        palette.setColor(palette.WindowText, QtGui.QColor(self.FOREGROUND_COLOR))  # Foreground
        self.setPalette(palette)
        pg.setConfigOption('background', QtGui.QColor(self.BACKGROUND_COLOR))
        pg.setConfigOption('foreground', QtGui.QColor(self.FOREGROUND_COLOR))
        # Set figure with pyqtgraph
        self._buffer_timestamp = None
        self._buffer_data = []
        self.last_plot_refresh = time()
        self.timeseries_widget = None
        self.init_timeseries_plot()
        # Set instrument
        if instrument:
            self.init_instrument(instrument)
        else:
            self.instrument = None
        self.packets_received = 0
        self.packets_logged = 0
        self.packets_corrupted = 0
        # Set buttons
        self.button_setup.clicked.connect(self.act_instrument_setup)
        self.button_serial.clicked.connect(self.act_instrument_serial)
        self.button_log.clicked.connect(self.act_instrument_log)
        # Set clock
        self.signal_clock = QtCore.QTimer()
        self.signal_clock.timeout.connect(self.set_clock)
        self.signal_clock.start(1000)
        # Plugins variables
        self.plugin_aux_data_variable_names = []
        self.plugin_aux_data_variable_values = []

    def init_instrument(self, instrument):
        self.instrument = instrument
        self.label_instrument_name.setText(self.instrument.name)
        self.instrument.signal.status_update.connect(self.on_status_update)
        self.instrument.signal.packet_received.connect(self.on_packet_received)
        self.instrument.signal.packet_corrupted.connect(self.on_packet_corrupted)
        self.instrument.signal.packet_logged.connect(self.on_packet_logged)
        self.instrument.signal.new_data.connect(self.on_new_data)
        self.on_status_update()  # Need to be run as on instrument setup the signals were not connected

        # Set Plugins specific to instrument
        # Auxiliary Data Plugin
        self.group_box_aux_data.setVisible(self.instrument.plugin_aux_data)
        if self.instrument.plugin_aux_data:
            # Set aux variable names
            for v in self.instrument.plugin_aux_data_variable_names:
                self.plugin_aux_data_variable_names.append(QtGui.QLabel(v))
                self.plugin_aux_data_variable_values.append(QtGui.QLabel('?'))
                self.group_box_aux_data_layout.addRow(self.plugin_aux_data_variable_names[-1],
                                                      self.plugin_aux_data_variable_values[-1])
            # Connect signal
            self.instrument.signal.new_aux_data.connect(self.on_new_aux_data)

        # Select Channels To Plot Plugin
        self.group_box_active_timeseries_variables.setVisible(self.instrument.plugin_active_timeseries_variables)
        if self.instrument.plugin_active_timeseries_variables:
            # Set sel channels check_box
            for v in self.instrument.plugin_active_timeseries_variables_names:
                check_box = QtWidgets.QCheckBox(v)
                check_box.stateChanged.connect(self.on_active_timeseries_variables_update)
                if v in self.instrument.plugin_active_timeseries_variables_selected:
                    check_box.setChecked(True)
                self.group_box_active_timeseries_variables_scroll_area_content_layout.addWidget(check_box)

    def init_timeseries_plot(self):
        # self.timeseries_widget = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem()}, enableMenu=False)  # Date Axis available in newer versions of pqtgraph
        # self.timeseries_widget = pg.PlotWidget(axisItems={'bottom': ReverseTimeAxisItem(self.BUFFER_LENGTH, 1, orientation='bottom')}, enableMenu=False)  # Disable time on bottom axis
        # self.timeseries_widget.plotItem.setLabel('bottom', 'Time since acquisition', units='mm:ss')
        self.timeseries_widget = pg.PlotWidget(
            axisItems={'bottom': ReverseAxisItem(self.BUFFER_LENGTH, orientation='bottom')}, enableMenu=False)
        self.timeseries_widget.plotItem.setLabel('bottom', 'Samples', units='#')
        self.timeseries_widget.plotItem.getAxis('bottom').enableAutoSIPrefix(False)
        self.timeseries_widget.plotItem.setLabel('left',
                                                 'Signal')  # Update units depending on instrument  #, units='Counts'
        self.timeseries_widget.plotItem.getAxis('left').enableAutoSIPrefix(False)
        self.timeseries_widget.plotItem.setLimits(minYRange=0, maxYRange=4500)  # In version 0.9.9
        self.timeseries_widget.plotItem.setMouseEnabled(x=False, y=True)
        self.timeseries_widget.plotItem.showGrid(x=False, y=True)
        self.timeseries_widget.plotItem.enableAutoRange(x=True, y=True)
        self.timeseries_widget.plotItem.addLegend()
        self.setCentralWidget(self.timeseries_widget)

    def set_clock(self):
        zulu = gmtime(time())
        self.label_clock.setText(strftime('%H:%M:%S', zulu) + ' UTC')
        # self.label_date.setText(strftime('%Y/%m/%d', zulu))

    def act_instrument_setup(self):
        logger.debug('Setup instrument')
        setup_dialog = DialogInstrumentSetup(self.instrument.cfg_id)
        setup_dialog.show()
        if setup_dialog.exec_():
            self.instrument.setup(setup_dialog.cfg)
            self.label_instrument_name.setText(self.instrument.name)

    def act_instrument_serial(self):
        if self.instrument.alive:
            logger.debug('Disconnect instrument')
            self.instrument.close()
        else:
            # TODO Update Connect Modal
            ports_list = list_serial_comports()
            ports_list_name = [str(p.device) + ' - ' + str(p.product) for p in ports_list]
            # Instrument need a port address to connect
            selected_port, ok = QtGui.QInputDialog.getItem(self, 'Connect Instrument',
                                                           'Connecting ' + self.instrument.name + '\nSelect port',
                                                           ports_list_name)
            if ok:
                port = ports_list[ports_list_name.index(selected_port)].device
                try:
                    self.instrument.open(port)
                except SerialException as e:
                    QtGui.QMessageBox.warning(self, "Connect " + self.instrument.name,
                                              'ERROR: Failed connecting ' + self.instrument.name + ' to ' +
                                              port + '\n' + str(e),
                                              QtGui.QMessageBox.Ok)

    def act_instrument_log(self):
        if self.instrument.log_active():
            logger.debug('Stop logging')
            self.instrument.log_stop()
        else:
            logger.debug('Start logging')
            self.instrument.log_start()

    @QtCore.pyqtSlot()
    def on_status_update(self):
        if self.instrument.alive:
            self.button_serial.setText('Close')
            self.button_serial.setToolTip('Disconnect instrument.')
            self.button_log.setEnabled(True)
            if self.instrument.log_active():
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
                self.label_instrument_name.setStyleSheet('font: 24pt;\ncolor: #ff9e17;')
                # Orange: #ff9e17 (darker) #ffc12f (lighter)
                self.button_log.setText('Start')
                self.button_log.setToolTip('Start logging data')
        else:
            self.label_status.setText('Disconnected')
            self.label_instrument_name.setStyleSheet('font: 24pt;\ncolor: #e0463e;')
            # Red: #e0463e (darker) #5cd9ef (lighter)  #f92670 (pyQtGraph)
            self.button_serial.setText('Open')
            self.button_serial.setToolTip('Connect instrument.')
            self.button_log.setEnabled(False)
        self.le_filename.setText(self.instrument.log_get_filename())
        self.le_directory.setText(self.instrument.log_get_path())
        self.packets_received = 0
        self.label_packets_received.setText(str(self.packets_received))
        self.packets_logged = 0
        self.label_packets_logged.setText(str(self.packets_logged))
        self.packets_corrupted = 0
        self.label_packets_corrupted.setText(str(self.packets_corrupted))

    @QtCore.pyqtSlot()
    def on_packet_received(self):
        self.packets_received += 1
        self.label_packets_received.setText(str(self.packets_received))

    @QtCore.pyqtSlot()
    def on_packet_logged(self):
        self.packets_logged += 1
        if self.packets_received < self.packets_logged < 2:  # Fix inconsistency when start logging
            self.packets_received = self.packets_logged
            self.label_packets_received.setText(str(self.packets_received))
        self.label_packets_logged.setText(str(self.packets_logged))

    @QtCore.pyqtSlot()
    def on_packet_corrupted(self):
        self.packets_corrupted += 1
        self.label_packets_corrupted.setText(str(self.packets_corrupted))

    @QtCore.pyqtSlot(list, float)
    @QtCore.pyqtSlot(np.ndarray, float)
    def on_new_data(self, data, timestamp):
        if len(self._buffer_data) != len(data):
            # Init buffers
            self._buffer_timestamp = RingBuffer(self.BUFFER_LENGTH)
            self._buffer_data = [RingBuffer(self.BUFFER_LENGTH) for i in range(len(data))]
            # Init Plot (need to do so when number of curve changes)
            self.init_timeseries_plot()
            # Init curves
            if self.instrument.plugin_active_timeseries_variables:
                legend = self.instrument.plugin_active_timeseries_variables_selected
            else:
                legend = self.instrument.variable_names
            for i in range(len(data)):
                self.timeseries_widget.plotItem.addItem(pg.PlotCurveItem(pen=(i, len(data)), name=legend[i]))
        # Update buffers
        self._buffer_timestamp.extend(timestamp)
        for i in range(len(data)):
            self._buffer_data[i].extend(data[i])
        # TODO Update real-time figure (depend on instrument type)
        # Update timeseries figure
        if time() - self.last_plot_refresh < 1 / self.MAX_PLOT_REFRESH_RATE:
            return
        # timestamp = self._buffer_timestamp.get(self.BUFFER_LENGTH)  # Not used anymore
        for i in range(len(data)):
            y = self._buffer_data[i].get(self.BUFFER_LENGTH)
            x = np.arange(len(y))
            sel = ~np.isnan(y)
            y[~sel] = np.interp(x[~sel], x[sel], y[sel])
            self.timeseries_widget.plotItem.items[i].setData(y, connect="finite")
            # TODO Put back X-Axis with time without high demand on cpu
            # self.timeseries_widget.plotItem.items[i].setData(timestamp[sel], y[sel], connect="finite")
        self.timeseries_widget.plotItem.enableAutoRange(x=True)  # Needed as somehow the user disable sometimes
        self.last_plot_refresh = time()

    @QtCore.pyqtSlot(list)
    def on_new_aux_data(self, data):
        if self.instrument.plugin_aux_data:
            for i, v in enumerate(data):
                self.plugin_aux_data_variable_values[i].setText(str(v))

    @QtCore.pyqtSlot(int)
    def on_active_timeseries_variables_update(self, state):
        if self.instrument.plugin_active_timeseries_variables:
            self.instrument.udpate_active_timeseries_variables(self.sender().text(), state)

    def closeEvent(self, event):
        reply = QtGui.QMessageBox.question(self, 'Closing application',
                                           "Are you sure to quit?", QtGui.QMessageBox.Yes |
                                           QtGui.QMessageBox.No, QtGui.QMessageBox.No)
        if reply == QtGui.QMessageBox.Yes:
            QtGui.QApplication.instance().closeAllWindows()  # NEEDED IF OTHER WINDOWS OPEN BY SPECIFIC INSTRUMENTS
            event.accept()
        else:
            event.ignore()


class DialogStartUp(QtGui.QDialog):
    LOAD_INSTRUMENT = 1
    SETUP_INSTRUMENT = 2

    def __init__(self):
        super(DialogStartUp, self).__init__()
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, 'startup.ui'), self)
        instruments_to_load = [i["manufacturer"] + ' ' + i["model"] + ' ' + i["serial_number"] for i in CFG.instruments]
        self.instruments_to_setup = [i[6:-3] for i in os.listdir(PATH_TO_RESOURCES) if i[-3:] == '.ui' and i[:6] == 'setup_']
        self.combo_box_instrument_to_load.addItems(instruments_to_load)
        self.combo_box_instrument_to_setup.addItems(self.instruments_to_setup)
        self.button_load.clicked.connect(self.act_load_instrument)
        self.button_setup.clicked.connect(self.act_setup_instrument)
        self.selection_index = None

    def act_load_instrument(self):
        self.selection_index = self.combo_box_instrument_to_load.currentIndex()
        self.done(self.LOAD_INSTRUMENT)

    def act_setup_instrument(self):
        self.selection_index = self.combo_box_instrument_to_setup.currentIndex()
        self.done(self.SETUP_INSTRUMENT)


class DialogInstrumentSetup(QtGui.QDialog):
    ENCODING = 'ascii'
    OPTIONAL_FIELDS = ['Variable Precision', 'Prefix Custom']

    def __init__(self, template):
        super(DialogInstrumentSetup, self).__init__()
        if isinstance(template, str):
            # Load template from instrument type
            self.create = True
            self.cfg_index = -1
            self.cfg = {'module': template}
            uic.loadUi(os.path.join(PATH_TO_RESOURCES, 'setup_' + template + '.ui'), self)
        elif isinstance(template, int):
            # Load from preconfigured instrument
            self.create = False
            self.cfg_index = template
            self.cfg = CFG.instruments[template]
            uic.loadUi(os.path.join(PATH_TO_RESOURCES, 'setup_' + self.cfg['module'] + '.ui'), self)
            # Populate fields
            for k, v in self.cfg.items():
                if hasattr(self, 'le_' + k):
                    if isinstance(v, bytes):
                        getattr(self, 'le_' + k).setText(v.decode().encode('unicode_escape').decode())
                    elif isinstance(v, list):
                        getattr(self, 'le_' + k).setText(', '.join([str(vv) for vv in v]))
                    else:
                        getattr(self, 'le_' + k).setText(v)
                elif hasattr(self, 'combobox_' + k):
                    if v:
                        getattr(self, 'combobox_' + k).setCurrentIndex(0)
                    else:
                        getattr(self, 'combobox_' + k).setCurrentIndex(1)
            # Populate special fields specific to each module
            if self.cfg['module'] == 'dataq':
                for c in self.cfg['channels_enabled']:
                    getattr(self, 'checkbox_channel%d_enabled' % (c + 1)).setChecked(True)
        else:
            raise ValueError('Invalid instance type for template.')
        if 'button_browse_log_directory' in self.__dict__.keys():
            self.button_browse_log_directory.clicked.connect(self.act_browse_log_directory)
        if 'button_browse_device_file' in self.__dict__.keys():
            self.button_browse_device_file.clicked.connect(self.act_browse_device_file)
        if 'button_browse_ini_file' in self.__dict__.keys():
            self.button_browse_ini_file.clicked.connect(self.act_browse_ini_file)

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

    def act_browse_ini_file(self):
        file_name, selected_filter = QtGui.QFileDialog.getOpenFileName(
            caption='Choose initialization file', filter='Ini File (*.ini)')
        self.le_ini_file.setText(file_name)

    def act_save(self):
        # Read form
        fields = [a for a in self.__dict__.keys() if 'combobox_' in a or 'le_' in a]
        empty_fields = list()
        for f in fields:
            field_prefix, field_name = f.split('_', 1)
            field_pretty_name = field_name.replace('_', ' ').title()
            if field_prefix == 'le':
                value = getattr(self, f).text()
                if not value:
                    empty_fields.append(field_pretty_name)
                    continue
                # Apply special formatting to specific variables
                try:
                    if 'variable_' in field_name:
                        value = value.split(',')
                        value = [v.strip() for v in value]
                        if 'variable_columns' in field_name:
                            value = [int(x) for x in value]
                    elif field_name in ['terminator', 'separator']:
                        # if len(value) > 3 and (value[:1] == "b'" and value[-1] == "'"):
                        #     value = bytes(value[2:-1], 'ascii')
                        value = value.strip().encode(self.ENCODING).decode('unicode_escape').encode(self.ENCODING)
                    else:
                        value.strip()
                except:
                    self.notification('Unable to parse special variable: ' + field_pretty_name, sys.exc_info()[0])
                    return
                self.cfg[field_name] = value
            elif field_prefix == 'combobox':
                if getattr(self, f).currentText() == 'on':
                    self.cfg[field_name] = True
                else:
                    self.cfg[field_name] = False
        # Read Log Prefix (not saved in cfg)
        self.cfg['log_prefix'] = ''
        if self.checkbox_prefix_diw.isChecked():
            self.cfg['log_prefix'] += 'DIW'
        if self.checkbox_prefix_fsw.isChecked():
            self.cfg['log_prefix'] += 'FSW'
        if self.checkbox_prefix_dark.isChecked():
            self.cfg['log_prefix'] += 'DARK'
        if self.checkbox_prefix_custom.isChecked():
            self.cfg['log_prefix'] += self.le_prefix_custom.text()
        self.cfg['log_prefix'] += '_'
        # Check All required fields are complete
        for f in self.OPTIONAL_FIELDS:
            try:
                empty_fields.pop(empty_fields.index(f))
            except ValueError:
                pass
        if empty_fields:
            self.notification('Fill required fields.', '\n'.join(empty_fields))
            return
        # Check generic special field
        if self.cfg['module'] == 'generic':
            variable_keys = [v for v in self.cfg.keys() if 'variable_' in v]
            if variable_keys:
                # Check length
                n = len(self.cfg['variable_names'])
                for k in variable_keys:
                    if n != len(self.cfg[k]):
                        self.notification('Inconsistent length. Variable Names, Variable Units, Variable Columns,'
                                          'Variable Types, and Variable Precision must have the same number of elements '
                                          'separated by commas.')
                        return
                # Check type
                for v in self.cfg['variable_types']:
                    if v not in ['int', 'float']:
                        self.notification('Invalid variable type')
                        return
                # Check precision
                if 'variable_precision' in self.cfg:
                    for v in self.cfg['variable_precision']:
                        if v[0] != '%' and v[-1] not in ['d', 'f']:
                            self.notification('Invalid variable precision. '
                                              'Expect type specific formatting (e.g. %d or %.3f) separated by commas.')
                            return
            if not self.cfg['log_raw'] and not self.cfg['log_products']:
                self.notification('Invalid logger configuration. '
                                  'At least one logger must be ON (to either log raw or parsed data).')
                return
        # Check ACS special fields
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
            except:
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
                self.cfg['serial_number'] = str(LISSTParser(self.cfg['device_file'], self.cfg['ini_file']).serial_number)
            except:
                self.notification('Unable to parse lisst device and/or ini file.')
                return
            if 'log_raw' not in self.cfg.keys():
                self.cfg['log_raw'] = True
            if 'log_products' not in self.cfg.keys():
                self.cfg['log_products'] = True
        elif self.cfg['module'] == 'dataq':
            self.cfg['channels_enabled'] = []
            for c in range(4):
                if getattr(self, 'checkbox_channel%d_enabled' % (c+1)).isChecked():
                    self.cfg['channels_enabled'].append(c)
            if not self.cfg['channels_enabled']:
                self.notification('At least one channel must be enabled.', 'Nothing to log if no channels are enabled.')
                return
            if 'log_raw' not in self.cfg.keys():
                self.cfg['log_raw'] = False
            if 'log_products' not in self.cfg.keys():
                self.cfg['log_products'] = True
        # Update global instrument cfg
        if self.create:
            CFG.instruments.append(self.cfg)
            self.cfg_index = -1
        else:
            CFG.instruments[self.cfg_index] = self.cfg.copy()
        CFG.write()
        self.accept()

    @staticmethod
    def notification(message, details=None):
        msg = QtGui.QMessageBox()
        msg.setIcon(QtGui.QMessageBox.Warning)
        msg.setText(message)
        # msg.setInformativeText("This is additional information")
        if details:
            msg.setDetailedText(str(details))
        msg.setWindowTitle("Inlinino: Setup Instrument Warning")
        msg.setStandardButtons(QtGui.QMessageBox.Ok)
        msg.exec_()


class App(QtGui.QApplication):
    def __init__(self, *args):
        QtGui.QApplication.__init__(self, *args)
        self.splash_screen = QtGui.QSplashScreen(QtGui.QPixmap(os.path.join(PATH_TO_RESOURCES, 'inlinino.ico')))
        self.splash_screen.show()
        self.main_window = MainWindow()
        self.startup_dialog = DialogStartUp()
        self.splash_screen.close()

    def start(self, instrument_index=None):
        if not instrument_index:
            logger.debug('Startup Dialog')
            self.startup_dialog.show()
            act = self.startup_dialog.exec_()
            if act == self.startup_dialog.LOAD_INSTRUMENT:
                instrument_index = self.startup_dialog.selection_index
            elif act == self.startup_dialog.SETUP_INSTRUMENT:
                setup_dialog = DialogInstrumentSetup(
                    self.startup_dialog.instruments_to_setup[self.startup_dialog.selection_index])
                setup_dialog.show()
                if setup_dialog.exec_():
                    instrument_index = setup_dialog.cfg_index
                else:
                    logger.info('Setup closed')
                    self.start()  # Restart application to go back to startup screen
            else:
                logger.info('Startup closed')
                sys.exit()

        # Load instrument
        instrument_name = CFG.instruments[instrument_index]['model'] + ' ' \
                          + CFG.instruments[instrument_index]['serial_number']
        instrument_module_name = CFG.instruments[instrument_index]['module']
        logger.debug('Loading instrument ' + instrument_name)
        if instrument_module_name == 'generic':
            self.main_window.init_instrument(Instrument(instrument_index, InstrumentSignals()))
        elif instrument_module_name == 'acs':
            self.main_window.init_instrument(ACS(instrument_index, InstrumentSignals()))
        elif instrument_module_name == 'dataq':
            self.main_window.init_instrument(DATAQ(instrument_index, InstrumentSignals()))
        elif instrument_module_name == 'lisst':
            self.main_window.init_instrument(LISST(instrument_index, InstrumentSignals()))
        else:
            logger.critical('Instrument module not supported')
            raise ValueError('Instrument module not supported')

        # Start Main Window
        self.main_window.show()
        sys.exit(self.exec_())

