from inlinino.instruments import Instrument
from inlinino.log import LogBinary
from pyACS.acs import ACS as ACSParser
from pyACS.acs import FrameIncompleteError, NumberWavelengthIncorrectError
import pyqtgraph as pg
from time import time


class ACS(Instrument):

    REGISTRATION_BYTES = b'\xff\x00\xff\x00'
    REQUIRED_CFG_FIELDS = ['device_file',
                           'model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_precision']

    def __init__(self, cfg_id, signal, *args, **kwargs):
        # ACS Specific attributes
        self._parser = None
        self.force_parsing = False  # TODO Add force parsing to GUI setup window
        self._timestamp_flag_out_T_cal = 0

        # Init Graphic for real time spectrum visualization
        # TODO Refactor code and move it to GUI
        # Set Color mode
        pg.setConfigOption('background', '#F8F8F2')
        pg.setConfigOption('foreground', '#26292C')
        self._pw = pg.plot(enableMenu=False)
        self._plot = self._pw.plotItem
        self._plot.addLegend()
        # Init Curve Items
        self._plot_curve_c = pg.PlotCurveItem(pen=(0, 2), name='c')
        self._plot_curve_a = pg.PlotCurveItem(pen=(1, 2), name='a')
        # Add item to plot
        self._plot.addItem(self._plot_curve_c)
        self._plot.addItem(self._plot_curve_a)
        # Decoration
        self._plot.setLabel('bottom', 'Wavelength' , units='nm')
        self._plot.setLabel('left', 'Signal', units='m<sup>-1</sup>')
        # self.m_plot.setYRange(0, 5)
        self._plot.setMouseEnabled(x=False, y=True)
        self._plot.showGrid(x=True, y=True)
        self._plot.enableAutoRange(x=True, y=True)
        self._plot.getAxis('left').enableAutoSIPrefix(False)

        super().__init__(cfg_id, signal, *args, **kwargs)

    def setup(self, cfg):
        # Set ACS specific attributes
        if 'device_file' not in cfg.keys():
            raise ValueError('Missing field device file')
        self._parser = ACSParser(cfg['device_file'])
        if 'force_parsing' in cfg.keys():
            self.force_parsing = cfg['force_parsing']
        # Overload cfg with ACS specific parameters
        cfg['variable_names'] = ['timestamp', 'c', 'a', 'T_int', 'T_ext', 'flag_outside_calibration_range']
        cfg['variable_units'] = ['ms', '1/m', '1/m', 'deg_C', 'deg_C', 'bool']
        cfg['variable_units'][1] = '1/m\tlambda=' + ' '.join('%s' % x for x in self._parser.lambda_c)
        cfg['variable_units'][2] = '1/m\tlambda=' + ' '.join('%s' % x for x in self._parser.lambda_a)
        cfg['variable_precision'] = ['%d', '%s', '%s', '%.6f', '%.6f', '%s']
        cfg['terminator'] = self.REGISTRATION_BYTES
        # Set standard configuration and check cfg input
        super().setup(cfg, LogBinary)
        # Update Plot config
        min_lambda = min(min(self._parser.lambda_c), min(self._parser.lambda_a))
        max_lambda = max(max(self._parser.lambda_c), max(self._parser.lambda_a))
        self._plot.setXRange(min_lambda, max_lambda)
        self._plot.setLimits(minXRange=min_lambda, maxXRange=max_lambda)

    def open(self, port=None, baudrate=None, bytesize=8, parity='N', stopbits=1, timeout=1):
        if baudrate is None:
            # Get default baudrate from device file via parser
            baudrate = self._parser.baudrate  # Default 115200
        super().open(port, baudrate, bytesize, parity, stopbits, timeout)

    def parse(self, packet):
        try:
            raw_frame = self._parser.unpack_frame(self.REGISTRATION_BYTES + packet, self.force_parsing)
            c, a, T_int, T_ext, flag_out_T_cal = self._parser.calibrate_frame(raw_frame, get_auxiliaries=True)
            return [raw_frame.time_stamp, c, a, T_int, T_ext, flag_out_T_cal]
        except FrameIncompleteError as e:
            self.signal.packet_corrupted.emit()
            self.logger.warning(e)
            self.logger.warning('This might happen on first packet received.')
        except NumberWavelengthIncorrectError as e:
            self.signal.packet_corrupted.emit()
            self.logger.warning(e)
            self.logger.warning('Likely due to invalid device file.')

    def handle_data(self, data, timestamp):
        # Update plots
        self.signal.new_data.emit([data[1][30], data[2][30]], timestamp)
        self._plot_curve_c.setData(self._parser.lambda_c, data[1])
        self._plot_curve_a.setData(self._parser.lambda_a, data[2])
        # Flag outside temperature calibration range
        if data[5] and time() - self._timestamp_flag_out_T_cal > 120:
            self._timestamp_flag_out_T_cal = time()
            self.logger.warning('Internal temperature outside calibration range.')
        # Log parsed data
        if self.log_prod_enabled and self._log_active:
            self._log_prod.write(data, timestamp)
            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()
