from inlinino.instruments import Instrument
from inlinino.log import LogBinary
from pyACS.acs import ACS as ACSParser
from pyACS.acs import FrameIncompleteError, NumberWavelengthIncorrectError
import pyqtgraph as pg


class ACS(Instrument):

    REGISTRATION_BYTES = b'\xff\x00\xff\x00'

    def __init__(self, name, cfg=None, ui=None, *args, **kwargs):
        # ACS Parser
        if 'device_file' not in cfg.keys():
            if __debug__:
                print(_name + ': Missing device file')
            exit()
        self._parser = ACSParser(cfg['device_file'])

        # Set/Check Configuration
        if 'force_parsing' not in cfg.keys():
            cfg['force_parsing'] = False
        if 'plot_spectrum' not in cfg.keys():
            cfg['plot_spectrum'] = True
        cfg['variable_names'] = ['timestamp', 'c', 'a', 'T_int', 'T_ext']
        cfg['variable_units'] = ['ms', '1/m', '1/m', 'deg_C', 'deg_C']
        cfg['variable_units'][1] = '1/m\tlambda=' + ' '.join('%s' % x for x in self._parser.lambda_c)
        cfg['variable_units'][2] = '1/m\tlambda=' + ' '.join('%s' % x for x in self._parser.lambda_a)
        cfg['variable_displayed'] = ['T_int', 'T_ext']
        cfg['variable_precision'] = ['%d', '%s', '%s', '%.6f', '%.6f']

        super().__init__(name, cfg, ui, *args, **kwargs)

        # Serial Specific to ACS
        self._serial.baudrate = 115200
        self._serial.bytesize = 8
        self._serial.parity = 'N'  # None
        self._serial.stopbits = 1
        self._serial.timeout = 1  # Instrument run at 4 Hz so let him a chance to speak
        self._terminator = self.REGISTRATION_BYTES

        # Logger
        self._log_raw = LogBinary(cfg)

        # ACS Specifics
        self.force_parsing = cfg['force_parsing']

        # self.variable_types = ['int', 'array', 'array', 'float', 'float']
        self.variable_precision = None  # TODO Implement precision for array

        # Init Graphic for real time spectrum visualization
        self.plot_spectrum = cfg['plot_spectrum']
        if self.plot_spectrum:
            # Set night mode
            # TODO get values from theme
            pg.setConfigOption('background', '#26292C')
            pg.setConfigOption('foreground', '#F8F8F2')
            self._pw = pg.plot(enableMenu=False)
            self._plot = self._pw.plotItem
            # Init Curve Items
            self._plot_curve_c = pg.PlotCurveItem(pen=(0, 2))
            self._plot_curve_a = pg.PlotCurveItem(pen=(1, 2))
            # Add item to plot
            self._plot.addItem(self._plot_curve_c)
            self._plot.addItem(self._plot_curve_a)
            # Decoration
            self._plot.setLabel('bottom', 'Wavelength' , units='nm')
            self._plot.setLabel('left', 'Signal', units='m^{-1}')
            # self.m_plot.setYRange(0, 5)
            # self.m_plot.setXRange(0, 100)
            self._plot.setLimits(minYRange=0, maxYRange=5)
            self._plot.setMouseEnabled(x=False, y=False)
            self._plot.showGrid(x=True, y=True)
            self._plot.enableAutoRange(x=True, y=True)

    def parse(self, packet):
        try:
            raw_frame = self._parser.unpack_frame(self.REGISTRATION_BYTES + packet, self.force_parsing)
            c, a, T_int, T_ext = self._parser.calibrate_frame(raw_frame, get_auxiliaries=True)
            # Update real-time plot
            if self.plot_spectrum:
                self._plot_curve_c.setData(self._parser.lambda_c, c)
                self._plot_curve_a.setData(self._parser.lambda_a, a)
            return [raw_frame.time_stamp, c, a, T_int, T_ext]
        except FrameIncompleteError as e:
            self.packet_corrupted += 1
            print(e)
            # self.CommunicationError(self.name + ' This might happen on first packet received.')
        except NumberWavelengthIncorrectError as e:
            self.packet_corrupted += 1
            print(e)
            # self.CommunicationError(self.name + ' Likely due to invalid device file.')
