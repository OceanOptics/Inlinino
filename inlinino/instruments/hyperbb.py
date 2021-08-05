from inlinino.instruments import Instrument
import pyqtgraph as pg
import configparser
import numpy as np
from time import sleep
from threading import Lock


class HyperBB(Instrument):

    REQUIRED_CFG_FIELDS = ['model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_precision']

    FRAME_VARIABLES = ['ScanIdx', 'DataIdx', 'Date', 'Time', 'StepPos', 'wl', 'LedPwr', 'PmtGain', 'NetSig1',
                       'SigOn1', 'SigOn1Std', 'RefOn', 'RefOnStd', 'SigOff1', 'SigOff1Std', 'RefOff',
                       'RefOffStd', 'SigOn2', 'SigOn2Std', 'SigOn3', 'SigOn3Std', 'SigOff2', 'SigOff2Std',
                       'SigOff3', 'SigOff3Std', 'LedTemp', 'WaterTemp', 'Depth', 'Debug1', 'zDistance']
    # FRAME_PRECISION = ['%d', '%d', '%s', '%s', '%d', '%d', '%d', '%d', '%d',
    #                    '%.1f', '%.1f', '%.1f', '%.1f', '%.1f', '%.1f', '%.1f',
    #                    '%.1f', '%.1f', '%.1f', '%.1f', '%.1f', '%.1f', '%.1f',
    #                    '%.1f', '%.1f', '%.2f', '%.2f', '%.2f', '%d', '%d']
    FRAME_PRECISION = ['%s'] * len(FRAME_VARIABLES)

    def __init__(self, cfg_id, signal, *args, **kwargs):
        self.wavelength = np.arange(430, 700, 10)  # TODO Import from Calibration file
        self.wl_idx = self.FRAME_VARIABLES.index('wl')
        self.sig_idx = self.FRAME_VARIABLES.index('NetSig1')
        self.ledtemp_idx = self.FRAME_VARIABLES.index('LedTemp')
        self.watertemp_idx = self.FRAME_VARIABLES.index('WaterTemp')
        self.depth_idx = self.FRAME_VARIABLES.index('Depth')
        self.signal_reconstructed = np.empty(len(self.wavelength))
        self.signal_reconstructed[:] = np.nan

        # Init Graphic for real time spectrum visualization
        # TODO Refactor code and move it to GUI
        # Set Color mode
        pg.setConfigOption('background', '#F8F8F2')
        pg.setConfigOption('foreground', '#26292C')
        self._pw = pg.plot(enableMenu=False)
        self._plot = self._pw.plotItem
        # Init Curve Items
        self._plot_curve = pg.PlotCurveItem(pen=pg.mkPen(color='#7f7f7f', width=2))
        # Add item to plot
        self._plot.addItem(self._plot_curve)
        # Decoration
        self._plot.setLabel('bottom', 'Wavelength', units='nm')
        self._plot.setLabel('left', 'Signal', units='counts')
        self._plot.setMouseEnabled(x=False, y=True)
        self._plot.showGrid(x=True, y=True)
        self._plot.enableAutoRange(x=True, y=True)
        self._plot.getAxis('left').enableAutoSIPrefix(False)
        self._plot.getAxis('bottom').enableAutoSIPrefix(False)
        # Set wavelength range
        self._plot.setXRange(np.min(self.wavelength), np.max(self.wavelength))
        self._plot.setLimits(minXRange=np.min(self.wavelength), maxXRange=np.max(self.wavelength))

        super().__init__(cfg_id, signal, *args, **kwargs)

        # Auxiliary Data Plugin
        self.plugin_aux_data = True
        self.plugin_aux_data_variable_names = ['LED Temp. (ºC)', 'Water Temp. (ºC)', 'Pressure (dBar)']

        # Select Channels to Plot Plugin
        self.plugin_active_timeseries_variables = True
        self.plugin_active_timeseries_variables_names = ['beta(%d)' % x for x in self.wavelength]
        self.plugin_active_timeseries_variables_selected = []
        self.active_timeseries_variables_lock = Lock()
        self.active_timeseries_wavelength = np.zeros(len(self.wavelength), dtype=bool)
        for wl in np.arange(450,700,50):
            channel_name = 'beta(%d)' % self.wavelength[np.argmin(np.abs(self.wavelength - wl))]
            self.udpate_active_timeseries_variables(channel_name, True)

    def setup(self, cfg):
        # Overload cfg
        cfg['variable_names'] = self.FRAME_VARIABLES
        cfg['variable_units'] = [''] * len(self.FRAME_VARIABLES)
        cfg['variable_precision'] = self.FRAME_PRECISION
        cfg['terminator'] = b'\n'
        # Set standard configuration and check cfg input
        super().setup(cfg)

    # def open(self, port=None, baudrate=19200, bytesize=8, parity='N', stopbits=1, timeout=10):
    #     super().open(port, baudrate, bytesize, parity, stopbits, timeout)

    def parse(self, packet):
        return packet.decode().split()

    def handle_data(self, data, timestamp):
        signal = np.empty(len(self.wavelength))
        signal[:] = np.nan
        try:
            sel = self.wavelength == int(data[self.wl_idx])
            signal[sel] = int(data[self.sig_idx])
            self.signal_reconstructed[sel] = int(data[self.sig_idx])
        except ValueError:
            # Unknown wavelength
            pass
        # Update plots
        if self.active_timeseries_variables_lock.acquire(timeout=0.125):
            try:
                self.signal.new_data.emit(signal[self.active_timeseries_wavelength], timestamp)
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update timeseries plot')
        self.signal.new_aux_data.emit([data[self.ledtemp_idx], data[self.watertemp_idx], data[self.depth_idx]])
        self._plot_curve.setData(self.wavelength, self.signal_reconstructed)
        # Log data as received
        if self.log_prod_enabled and self._log_active:
            self._log_prod.write(data, timestamp)
            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()

    def udpate_active_timeseries_variables(self, name, state):
        if not ((state and name not in self.plugin_active_timeseries_variables_selected) or
                (not state and name in self.plugin_active_timeseries_variables_selected)):
            return
        if self.active_timeseries_variables_lock.acquire(timeout=0.125):
            try:
                index = self.plugin_active_timeseries_variables_names.index(name)
                self.active_timeseries_wavelength[index] = state
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update active timeseries variables')
        # Update list of active variables for GUI keeping the order
        self.plugin_active_timeseries_variables_selected = \
            ['beta(%d)' % wl for wl in self.wavelength[self.active_timeseries_wavelength]]
