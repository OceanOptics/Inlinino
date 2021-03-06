from inlinino.instruments import Instrument
import pyqtgraph as pg
import configparser
import numpy as np
from time import sleep
from threading import Lock


class LISST(Instrument):

    REQUIRED_CFG_FIELDS = ['ini_file', 'device_file',
                           'model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_precision']

    def __init__(self, cfg_id, signal, *args, **kwargs):
        self._parser = None

        # Init Graphic for real time spectrum visualization
        # TODO Refactor code and move it to GUI
        # Set Color mode
        pg.setConfigOption('background', '#F8F8F2')
        pg.setConfigOption('foreground', '#26292C')
        self._pw = pg.plot(enableMenu=False)
        self._plot = self._pw.plotItem
        self._plot.setLogMode(x=True)
        # Init Curve Items
        self._plot_curve = pg.PlotCurveItem(pen=(0, 1))
        # Add item to plot
        self._plot.addItem(self._plot_curve)
        # Decoration
        self._plot.setLabel('bottom', 'Angles', units='degrees')
        self._plot.setLabel('left', 'Signal', units='counts')
        self._plot.setMouseEnabled(x=False, y=True)
        self._plot.showGrid(x=True, y=True)
        self._plot.enableAutoRange(x=True, y=True)
        self._plot.getAxis('left').enableAutoSIPrefix(False)
        self._plot.getAxis('bottom').enableAutoSIPrefix(False)
        super().__init__(cfg_id, signal, *args, **kwargs)

        # Auxiliary Data Plugin
        self.plugin_aux_data = True
        self.plugin_aux_data_variables_selected = [0, 3, 5]
        self.plugin_aux_data_variable_names = [self._parser.aux_labels[i] + ' (' + self._parser.aux_units[i] + ')' \
                                               for i in self.plugin_aux_data_variables_selected]

        # Select Channels to Plot Plugin
        self.plugin_active_timeseries_variables = True
        self.plugin_active_timeseries_variables_names = ['beta(%.5f)' % x for x in self._parser.angles]
        self.plugin_active_timeseries_variables_selected = []
        self.active_timeseries_variables_lock = Lock()
        self.active_timeseries_angles = np.zeros(len(self._parser.angles), dtype=bool)
        for theta in [0.08, 0.32, 1.28, 5.12]:
            channel_name = 'beta(%.5f)' % self._parser.angles[np.argmin(np.abs(self._parser.angles - theta))]
            self.udpate_active_timeseries_variables(channel_name, True)

    def setup(self, cfg):
        # Set LISST specific attributes
        if 'ini_file' not in cfg.keys():
            raise ValueError('Missing ini file (Lisst.ini)')
        if 'device_file' not in cfg.keys():
            raise ValueError('Missing instrument file (InstrumentData.txt)')
        self._parser = LISSTParser(cfg['device_file'], cfg['ini_file'])
        # Overload cfg with LISST specific parameters
        cfg['variable_names'] = ['beta']
        cfg['variable_names'].extend(self._parser.aux_names)
        cfg['variable_units'] = ['counts\tangle=' + ' '.join('%.2f' % x for x in self._parser.angles)]
        cfg['variable_units'].extend(self._parser.aux_units)
        cfg['variable_precision'] = ['%s', '%.6f', '%.2f', '%.2f', '%.6f', '%.2f', '%.2f', "%.6f"]
        cfg['terminator'] = b'L100x:>'
        # Set standard configuration and check cfg input
        super().setup(cfg)
        # Update logger configuration
        self._log_raw.registration = self._terminator.decode(self._parser.ENCODING, self._parser.UNICODE_HANDLING)
        self._log_raw.terminator = ''  # Remove terminator
        self._log_raw.variable_names = []  # Disable header in raw file
        # Update plot with config
        self._plot.setXRange(np.min(self._parser.angles), np.max(self._parser.angles))
        self._plot.setLimits(minXRange=np.min(self._parser.angles), maxXRange=np.max(self._parser.angles))

    def open(self, port=None, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=10):
        super().open(port, baudrate, bytesize, parity, stopbits, timeout)

    def parse(self, packet):
        raw_beta, raw_aux = self._parser.unpack_packet(packet)
        aux = self._parser.calibrate_auxiliaries(raw_aux)
        return [raw_beta] + aux.tolist()

    def handle_data(self, data, timestamp):
        # Update plots
        if self.active_timeseries_variables_lock.acquire(timeout=0.5):
            try:
                self.signal.new_data.emit(data[1][self.active_timeseries_angles], timestamp)
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update timeseries plot')
        self.signal.new_data.emit(data[0][15], timestamp)
        self.signal.new_aux_data.emit(self.format_aux_data([data[i+1] for i in self.plugin_aux_data_variables_selected]))
        self._plot_curve.setData(self._parser.angles, data[0])
        if self.log_prod_enabled and self._log_active:
            # np arrays must be pre-formated to be written
            data[0] = np.array2string(data[0], max_line_width=np.inf)
            self._log_prod.write(data, timestamp)
            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()

    def init_serial(self):
        # TODO Check if OM, BI, SB, SI commands are necessary
        # TODO Check if configuration is correct
        self._serial.write(b'OM 1' + bytes(self._parser.LINE_ENDING, self._parser.ENCODING))    # Operating Mode: Real Time
        self._serial.write(b'BI 6' + bytes(self._parser.LINE_ENDING, self._parser.ENCODING))    # Seconds between Bursts: 6
        self._serial.write(b'SB 1' + bytes(self._parser.LINE_ENDING, self._parser.ENCODING))    # Samples per Burst: 1
        self._serial.write(b'SI 6' + bytes(self._parser.LINE_ENDING, self._parser.ENCODING))    # Seconds between Samples: 6
        self._serial.write(b'MA 250' + bytes(self._parser.LINE_ENDING, self._parser.ENCODING))  # Measurements per Average: 250
        sleep(0.1)
        response = self._serial.read(self._serial.in_waiting)
        # Query first data
        self._serial.write(b'GX' + bytes(self._parser.LINE_ENDING, self._parser.ENCODING))

    def write_to_serial(self):
        self._serial.write(b'GX' + bytes(self._parser.LINE_ENDING, self._parser.ENCODING))

    @staticmethod
    def format_aux_data(data):
        return ['%.2f' % v for v in data]

    def udpate_active_timeseries_variables(self, name, state):
        if not ((state and name not in self.plugin_active_timeseries_variables_selected) or
                (not state and name in self.plugin_active_timeseries_variables_selected)):
            return
        if self.active_timeseries_variables_lock.acquire(timeout=0.25):
            try:
                index = self.plugin_active_timeseries_variables_names.index(name)
                self.active_timeseries_angles[index] = state
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update active timeseries variables')
        # Update list of active variables for GUI keeping the order
        self.plugin_active_timeseries_variables_selected = \
            ['beta(%.5f)' % theta for theta in self._parser.angles[self.active_timeseries_angles]]


class LISSTParser:

    ENCODING = 'utf-8'
    UNICODE_HANDLING = 'replace'
    LINE_ENDING = '\r\n'
    AUX_N = 6
    INDEX_DD_HH = AUX_N
    INDEX_MM_SS = INDEX_DD_HH + 1

    def __init__(self, instrument_file, ini_file):

        # Instrument Parameters
        with open(instrument_file) as f:
            foo = f.readline().split(',')
            self.serial_number = int(foo[0])
            self.type = foo[1].strip()
            self.vcc = int(foo[3])  # Volume Conversion Constant

        if self.type not in ['b', 'c']:
            raise ValueError('Unknown LISST Type ' + str(self.type))

        # Get angles
        rho = 200 ** (1 / 32)
        if self.type == 'b':
            dynamic_range_start = 0.1
        elif self.type == 'c':
            dynamic_range_start = 0.05
        refractive_index_water = 1.33
        self.bin_edges = np.logspace(0, np.log10(200), 33) * dynamic_range_start / refractive_index_water
        self.angles = np.sqrt(self.bin_edges[:32] * self.bin_edges[1:33])

        # Auxiliary calibration parameters
        ini = configparser.ConfigParser()
        ini.read(ini_file)
        instrument_key = 'Instrument' + str(self.serial_number)
        if instrument_key not in ini.sections():
            raise ValueError("Initialization file (" + ini_file + ") does not contain the instrument specified in " +
                             ini_file)

        self.aux_names = ['laser_power', 'battery', 'ext_instr', 'laser_reference', 'depth', 'temperature', 'timestamp']
        self.aux_labels, self.aux_units, self.aux_scales, self.aux_offs = [], [], [], []
        self.off = []
        for i in range(self.AUX_N):
            self.aux_labels.append(ini[instrument_key]['HK' + str(i) + 'Label'])
            self.aux_units.append(ini[instrument_key]['HK' + str(i) + 'Units'])
            self.aux_scales.append(float(ini[instrument_key]['HK' + str(i) + 'Scale']))
            self.aux_offs.append(float(ini[instrument_key]['HK' + str(i) + 'Off']))
        self.aux_scales = np.asarray(self.aux_scales)
        self.aux_offs = np.asarray(self.aux_offs)
        # Special Aux for day and time
        self.aux_labels.append('Day')
        self.aux_units.append('decimal day')

    def unpack_packet(self, packet):
        try:
            packet = packet.decode(self.ENCODING, self.UNICODE_HANDLING)
            data = np.asarray(packet[packet.find('{')+2:packet.find('}')-1].split(self.LINE_ENDING), dtype='int')
        except:
            raise UnexpectedPacket('Unable to parse input into numpy array')
        if len(data) != 40:
            raise UnexpectedPacket('Incorrect number of variables in packet')
        return data[:32], data[32:]

    def calibrate_auxiliaries(self, raw):
        if len(raw) != self.AUX_N + 2:
            raise UnexpectedAuxiliaries('Incorrect number of auxiliary parameters')
        data = self.aux_scales * np.asarray(raw[:self.AUX_N]) + self.aux_offs
        decimal_day = raw[self.INDEX_DD_HH] // 100 + (raw[self.INDEX_DD_HH] % 100) / 24 +\
                      raw[self.INDEX_MM_SS] // 100 / 1440 + (raw[self.INDEX_MM_SS] % 100) / 86400
        return np.append(data, decimal_day)


# Error Management
class LISSTError(Exception):
    pass


class UnexpectedPacket(LISSTError):
    pass


class UnexpectedAuxiliaries(LISSTError):
    pass
