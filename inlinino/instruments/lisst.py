from inlinino.instruments import Instrument
import pyqtgraph as pg
import configparser
import numpy as np
from time import sleep


class LISST(Instrument):

    def __init__(self, name, cfg=None, ui=None, *args, **kwargs):
        # ACS Parser
        if 'ini_file' not in cfg.keys():
            if __debug__:
                print(name + ': Missing ini file (Lisst.ini)')
            exit()
        if 'instrument_file' not in cfg.keys():
            if __debug__:
                print(name + ': Missing instrument file (InstrumentData.txt)')
            exit()
        self._parser = LISSTParser(cfg['instrument_file'], cfg['ini_file'])

        # Set/Check Configuration
        if 'plot_spectrum' not in cfg.keys():
            cfg['plot_spectrum'] = True
        if 'plot_semilog_x' not in cfg.keys():
            cfg['plot_semilog_x'] = True
        cfg['variable_names'] = ['beta']
        cfg['variable_names'].extend(self._parser.aux_names)
        cfg['variable_units'] = ['counts\tangle=' + ' '.join('%.2f' % x for x in self._parser.angles)]
        cfg['variable_units'].extend(self._parser.aux_units)
        cfg['variable_displayed'] = ['laser_power', 'laser_reference', 'depth', 'temperature']
        cfg['variable_precision'] = ['%s', '%.6f', '%.2f', '%.2f', '%.6f', '%.2f', '%.2f', "%.6f"]

        super().__init__(name, cfg, ui, *args, **kwargs)

        # Serial Specific to LISST
        self._serial.baudrate = 9600
        self._serial.bytesize = 8
        self._serial.parity = 'N'  # None
        self._serial.stopbits = 1
        self._serial.timeout = 10  # Instrument average many points before sampling
        self._terminator = b'L100x:>'

        # Logger specific to LISST
        self._log_raw.registration = self._terminator.decode(self._parser.ENCODING, self._parser.UNICODE_HANDLING)
        self._log_raw.terminator = ''      # Remove terminator
        self._log_raw.variable_names = []  # Disable header in raw file

        # Init Graphic for real time spectrum visualization
        self.plot_spectrum = cfg['plot_spectrum']
        self.plot_semilog_x = cfg['plot_semilog_x']
        if self.plot_spectrum:
            # Set night mode
            # TODO get values from theme
            pg.setConfigOption('background', '#26292C')
            pg.setConfigOption('foreground', '#F8F8F2')
            self._pw = pg.plot(enableMenu=False)
            self._plot = self._pw.plotItem
            if self.plot_semilog_x:
                self._plot.setLogMode(x=True)
            # Init Curve Items
            self._plot_curve = pg.PlotCurveItem(pen=(0, 1))
            # Add item to plot
            self._plot.addItem(self._plot_curve)
            # Decoration
            self._plot.setLabel('bottom', 'Angles' , units='degrees')
            self._plot.setLabel('left', 'Signal', units='counts')
            # self._plot.setYRange(0, 5)
            self._plot.setXRange(np.min(self._parser.angles), np.max(self._parser.angles))
            self._plot.setLimits(minXRange=np.min(self._parser.angles), maxXRange=np.max(self._parser.angles))
            self._plot.setMouseEnabled(x=False, y=False)
            self._plot.showGrid(x=True, y=True)
            self._plot.enableAutoRange(x=True, y=True)
            self._plot.getAxis('left').enableAutoSIPrefix(False)


    def parse(self, packet):
        raw_beta, raw_aux = self._parser.unpack_packet(packet)
        aux = self._parser.calibrate_auxiliaries(raw_aux)
        if self.plot_spectrum:
            self._plot_curve.setData(self._parser.angles, raw_beta)
        return [raw_beta] + aux.tolist()

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
            raise ValueError('Invalid LISST Type ' + str(self.type))

        # Get angles
        rho = 200 ** (1 / 32)
        if self.type == 'b':
            dynamic_range_start = 0.1
        elif self.type == 'c':
            dynamic_range_start = 0.05
        refractive_index_water = 1.33
        foo = np.logspace(0, np.log10(200), 33) * dynamic_range_start / refractive_index_water
        self.angles_lower_lim = foo[:32]
        self.angles_upper_lim = foo[1:33]
        self.angles = np.sqrt(self.angles_lower_lim * self.angles_upper_lim)

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
