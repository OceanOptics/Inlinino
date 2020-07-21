from pyqtgraph.Qt import QtGui, QtCore, QtWidgets, uic
import pyqtgraph as pg
import sys, os
import logging
import importlib
from time import time, gmtime, strftime
from serial.tools.list_ports import comports as list_serial_comports
from serial import SerialException
from inlinino import RingBuffer, CFG, __version__
from inlinino.instruments import Instrument
from pyACS.acs import ACS as ACSParser
from inlinino.instruments.lisst import LISSTParser
import numpy as np

logger = logging.getLogger('GUI')
APP_ICON = 'resources/inlinino.ico'


class InstrumentSignals(QtCore.QObject):
    status_update = QtCore.pyqtSignal()
    packet_received = QtCore.pyqtSignal()
    packet_corrupted = QtCore.pyqtSignal()
    packet_logged = QtCore.pyqtSignal()
    new_data = QtCore.pyqtSignal(object, object)


class DateAxis(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        pg.AxisItem.__init__(self, *args, **kwargs)

    def tickStrings(self, values, scale, spacing):
        strns = []
        if values:
            rng = max(values) - min(values)
            # if rng < 120:
            #    return pg.AxisItem.tickStrings(self, values, scale, spacing)
            if rng < 3600 * 24:
                string = '%H:%M:%S'
                label1 = '%b %d - '
                label2 = '%d, %Y'
            elif rng >= 3600 * 24 and rng < 3600 * 24 * 30:
                string = '%d'
                label1 = '%b - '
                label2 = '%b,  %Y'
            elif rng >= 3600 * 24 * 30 and rng < 3600 * 24 * 30 * 24:
                string = '%b'
                label1 = '%Y -'
                label2 = ' %Y'
            elif rng >= 3600 * 24 * 30 * 24:
                string = '%Y'
                label1 = ''
                label2 = ''
            for x in values:
                try:
                    strns.append(strftime(string, gmtime(x)))
                except ValueError:  # Windows can't handle dates before 1970
                    strns.append('')
            # try:
            #     label = strftime(label1, gmtime(min(values))) + \
            #             strftime(label2, gmtime(max(values)))
            # except ValueError:
            #     label = ''
            # self.setLabel(text=label)
            return strns
        else:
            return []


class MainWindow(QtGui.QMainWindow):
    BACKGROUND_COLOR = '#F8F8F2'
    FOREGROUND_COLOR = '#26292C'
    BUFFER_LENGTH = 240
    MAX_PLOT_REFRESH_RATE = 2   # Hz

    def __init__(self, instrument=None):
        super(MainWindow, self).__init__()
        uic.loadUi(os.path.join('resources', 'main.ui'), self)
        # Graphical Adjustments
        self.dock_widget.setTitleBarWidget(QtGui.QWidget(None))
        self.label_app_version = 'v' + __version__
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
        self.timeseries_widget = pg.PlotWidget(axisItems={'bottom': DateAxis(orientation='bottom')}, enableMenu=False)
        self.timeseries_widget.plotItem.setLabel('left', 'Signal')  # Update units depending on instrument  #, units='Counts'
        self.timeseries_widget.plotItem.setLimits(minYRange=0, maxYRange=4500)  # In version 0.9.9
        self.timeseries_widget.plotItem.setMouseEnabled(x=False, y=True)
        self.timeseries_widget.plotItem.showGrid(x=False, y=True)
        self.timeseries_widget.plotItem.enableAutoRange(x=True, y=True)
        self.timeseries_widget.plotItem.getAxis('left').enableAutoSIPrefix(False)
        self.setCentralWidget(self.timeseries_widget)
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

    def init_instrument(self, instrument):
        self.instrument = instrument
        self.label_instrument_name.setText(self.instrument.name)
        self.instrument.signal.status_update.connect(self.on_status_update)
        self.instrument.signal.packet_received.connect(self.on_packet_received)
        self.instrument.signal.packet_corrupted.connect(self.on_packet_corrupted)
        self.instrument.signal.packet_logged.connect(self.on_packet_logged)
        self.instrument.signal.new_data.connect(self.on_new_data)
        self.on_status_update()  # Need to be run as on instrument setup the signals were not connected

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
            logger.debug('Connect instrument')
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

    def on_packet_received(self):
        self.packets_received += 1
        self.label_packets_received.setText(str(self.packets_received))

    def on_packet_logged(self):
        self.packets_logged += 1
        if self.packets_received < self.packets_logged < 2:  # Fix inconsistency when start logging
            self.packets_received = self.packets_logged
            self.label_packets_received.setText(str(self.packets_received))
        self.label_packets_logged.setText(str(self.packets_logged))

    def on_packet_corrupted(self):
        self.packets_corrupted += 1
        self.label_packets_corrupted.setText(str(self.packets_corrupted))

    def on_new_data(self, data, timestamp):
        if self._buffer_timestamp is None:
            # Init buffers
            self._buffer_timestamp = RingBuffer(self.BUFFER_LENGTH)
            self._buffer_data = [RingBuffer(self.BUFFER_LENGTH) for i in range(len(data))]
            # Init curves
            for i in range(len(data)):
                self.timeseries_widget.plotItem.addItem(pg.PlotCurveItem(pen=(i, len(data))))
        else:
            # Update buffers
            self._buffer_timestamp.extend(timestamp)
            for i in range(len(data)):
                self._buffer_data[i].extend(data[i])
        # TODO Update real-time figure (depend on instrument type)
        # Update timeseries figure
        if time() - self.last_plot_refresh < 1 / self.MAX_PLOT_REFRESH_RATE:
            return
        timestamp = self._buffer_timestamp.get(self.BUFFER_LENGTH)
        for i in range(len(data)):
            y = self._buffer_data[i].get(self.BUFFER_LENGTH)
            sel = ~np.isnan(y)
            self.timeseries_widget.plotItem.items[i].setData(timestamp[sel], y[sel], connect="finite")
        self.timeseries_widget.plotItem.enableAutoRange(x=True)  # Needed as somehow the user disable sometimes
        self.last_plot_refresh = time()

    def closeEvent(self, event):
        reply = QtGui.QMessageBox.question(self, 'Closing application',
                                           "Are you sure to quit?", QtGui.QMessageBox.Yes |
                                           QtGui.QMessageBox.No, QtGui.QMessageBox.No)
        if reply == QtGui.QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()


class DialogStartUp(QtGui.QDialog):
    LOAD_INSTRUMENT = 1
    SETUP_INSTRUMENT = 2

    def __init__(self):
        super(DialogStartUp, self).__init__()
        uic.loadUi(os.path.join('resources', 'startup.ui'), self)
        instruments_to_load = [i["manufacturer"] + ' ' + i["model"] + ' ' + i["serial_number"] for i in CFG.instruments]
        self.instruments_to_setup = [i[:-3] for i in os.listdir('instruments/') if i[-3:] == '.py']
        self.instruments_to_setup[self.instruments_to_setup.index('__init__')] = 'generic'
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
            uic.loadUi(os.path.join('resources', 'setup_' + template + '.ui'), self)
        elif isinstance(template, int):
            # Load from preconfigured instrument
            self.create = False
            self.cfg_index = template
            self.cfg = CFG.instruments[template]
            uic.loadUi(os.path.join('resources', 'setup_' + self.cfg['module'] + '.ui'), self)
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

    def act_browse_log_directory(self):
        self.le_log_path.setText(QtGui.QFileDialog.getExistingDirectory(caption='Choose logging directory'))

    def act_browse_device_file(self):
        file_name, selected_filter = QtGui.QFileDialog.getOpenFileName(
            caption='Choose device file', filter='Device File (*.dev, *.txt)')
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
                logger.warning('Unable to parse acs device file.')
                return
        elif self.cfg['module'] == 'lisst':
            self.cfg['manufacturer'] = 'Sequoia'
            self.cfg['model'] = 'LISST'
            try:
                self.cfg['serial_number'] = str(LISSTParser(self.cfg['device_file'], self.cfg['ini_file']).serial_number)
            except:
                logger.warning('Unable to parse lisst device and/or ini file.')
                return
        # Update global instrument cfg
        if self.create:
            CFG.instruments.append(self.cfg)
            self.cfg_index = -1
        else:
            CFG.instruments[self.cfg_index] = self.cfg
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
        self.splash_screen = QtGui.QSplashScreen(QtGui.QPixmap(APP_ICON))
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
        else:
            module = importlib.import_module('inlinino.instruments.' + instrument_module_name)
            self.main_window.init_instrument(
                getattr(module, instrument_module_name.upper())(instrument_index, InstrumentSignals()))

        # Start Main Window
        self.main_window.show()
        sys.exit(self.exec_())
