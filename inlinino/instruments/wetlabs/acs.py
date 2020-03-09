from instruments import Instrument
from instruments.wetlabs import WETLabs
from pyACS.acs import ACS as ACSParser
from pyACS.acs import FrameIncompleteError, NumberWavelengthIncorrectError
from serial import Serial
from itertools import repeat
import pyqtgraph as pg


class ACS(WETLabs):

    BYTES_TO_READ = 785
    REGISTRATION_BYTES = b'\xff\x00\xff\x00'
    MAX_BUFFER_LENGTH = 10000

    def __init__(self, _name, _cfg):
        Instrument.__init__(self, _name)
        # WETLabs.__init__(self, _name, _cfg) # ACS is too specific so skip general init of WETLabs
        # No Responsive Counter
        self.m_maxNoResponse = 10
        self.m_connect_need_port = True
        # Serial Communication
        self.m_serial = Serial()
        self.m_serial.baudrate = 115200
        self.m_serial.bytesize = 8
        self.m_serial.parity = 'N'  # None
        self.m_serial.stopbits = 1
        self.m_serial.timeout = 1  # Instrument run at 4 Hz so let him a chance to speak
        # ACS Specifics
        self.m_varnames = ['timestamp', 'c', 'a', 'T_int', 'T_ext']
        self.m_units = {'timestamp': 'ms', 'c': '1/m', 'a': '1/m', 'T_int': 'deg_C', 'T_ext': 'deg_C'}
        self.m_vardisplayed = {'timestamp': False, 'c': False, 'a': False, 'T_int': True, 'T_ext': True}
        self.m_vartype = {'timestamp': 'int', 'c': 'array', 'a': 'array', 'T_int': 'float', 'T_ext': 'float'}
        self.m_cache = dict(zip(self.m_varnames, repeat(None)))
        self.m_cacheIsNew = dict(zip(self.m_varnames, repeat(False)))
        self._buffer = bytearray()

        # Init ACS object
        if 'device_file' not in _cfg.keys():
            if __debug__:
                print(_name + ': Missing device file')
            exit()
        self._parser = ACSParser(_cfg['device_file'])
        # Insert wavelengths in units
        self.m_units['c'] = '1/m\tlambda=' + ' '.join('%s' % x for x in self._parser.lambda_c)
        self.m_units['a'] = '1/m\tlambda=' + ' '.join('%s' % x for x in self._parser.lambda_a)

        # Init Graphique for real time spectrum visualization
        if 'plot_spectrum' in _cfg.keys():
            self.m_plot_spectrum = _cfg['plot_spectrum']
        else:
            self.m_plot_spectrum = False
        if self.m_plot_spectrum:
            # Set night mode
            pg.setConfigOption('background', '#26292C')
            pg.setConfigOption('foreground', '#F8F8F2')
            self.m_pw = pg.plot(enableMenu=False)
            self.m_plot = self.m_pw.plotItem
            # Init Curve Items
            self.m_curve_c = pg.PlotCurveItem(pen=(0, 2))
            self.m_curve_a = pg.PlotCurveItem(pen=(1, 2))
            # Add item to plot
            self.m_plot.addItem(self.m_curve_c)
            self.m_plot.addItem(self.m_curve_a)
            # Decoration
            self.m_plot.setLabel('bottom', 'Wavelength' , units='nm')
            self.m_plot.setLabel('left', 'Signal', units='m^{-1}')
            # self.m_plot.setYRange(0, 5)
            # self.m_plot.setXRange(0, 100)
            self.m_plot.setLimits(minYRange=0, maxYRange=5)
            self.m_plot.setMouseEnabled(x=False, y=False)
            self.m_plot.showGrid(x=True, y=True)
            self.m_plot.enableAutoRange(x=True, y=True)

    def UpdateCache(self):
        self.ReadData()

    def ReadData(self):
        self._buffer.extend(self.m_serial.read(self.BYTES_TO_READ))
        while self.REGISTRATION_BYTES in self._buffer:
            frame, self._buffer = self._buffer.split(self.REGISTRATION_BYTES, 1)
            if frame:
                self.HandleFrame(frame)
        if len(self._buffer) > self.MAX_BUFFER_LENGTH:
            self.CommunicationError('Buffer exceeded maximum length. Buffer emptied to prevent overflow.\n' +
                                    'Is the registration byte correct ? Is the correct instrument selected ?')
            self._buffer = bytearray()

    def HandleFrame(self, frame):
        # ts = int(time.time() * 1000)  # Host timestamp different from ACS internal timestamp
        try:
            raw_frame = self._parser.unpack_frame(self.REGISTRATION_BYTES + frame)
            cal_frame = self._parser.calibrate_frame(raw_frame, True)  # return tuple (c, a, int_t_su, ext_t_su)
            self.m_cache = {'timestamp': raw_frame.time_stamp,
                            'c': str(cal_frame[0]), 'a': str(cal_frame[1]),
                            'T_int': cal_frame[2], 'T_ext': cal_frame[3]}
            # Trigger event for new data
            self.m_cacheIsNew = {'timestamp': True, 'c': True, 'a': True, 'T_int': True, 'T_ext': True}
            # Update counter
            self.m_n += 1
            # Update real-time plot
            if self.m_plot_spectrum:
                self.m_curve_c.setData(self._parser.lambda_c, cal_frame[0])
                self.m_curve_a.setData(self._parser.lambda_a, cal_frame[1])
        except FrameIncompleteError as e:
            print(e)
            self.CommunicationError('This might happen on few first ' +
                                    'bytes received.\nIf it keeps going ' +
                                    'try disconnecting and reconnecting ' +
                                    'the instrument.')
        except NumberWavelengthIncorrectError as e:
            print(e)
            self.CommunicationError('Likely due to invalid device file.')
