from collections import namedtuple

from inlinino.instruments import Instrument
import pyqtgraph as pg
import numpy as np


class Suna(Instrument):
    REQUIRED_CFG_FIELDS = ['calibration_file',
                           'model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_precision']
    N_CHANNELS = 256
    CHANNELS_START_IDX = 11
    CHANNELS_END_IDX = CHANNELS_START_IDX + N_CHANNELS

    def __init__(self, cfg_id, signal, *args, **kwargs):
        # Suna specific
        self.df_maker = None
        self.wavelength = [c for c in range(self.N_CHANNELS)]  # TODO Get wavelengths registration from calibration file

        # Init Graphic for real time spectrum visualization
        # TODO Refactor code and move it to GUI
        # Set Color mode
        pg.setConfigOption('background', '#F8F8F2')
        pg.setConfigOption('foreground', '#26292C')
        self._pw = pg.plot(enableMenu=False)
        self._pw.setWindowTitle('Suna Spectra')
        self._plot = self._pw.plotItem
        self._plot.addLegend()
        # Init Curve Items
        self._plot_curve_light = pg.PlotCurveItem(pen=pg.mkPen(color='#1f77b4', width=2), name='light')
        self._plot_curve_dark = pg.PlotCurveItem(pen=pg.mkPen(color='#2ca02c', width=2), name='dark')
        # Add item to plot
        self._plot.addItem(self._plot_curve_light)
        self._plot.addItem(self._plot_curve_dark)
        # Decoration
        self._plot.setLabel('bottom', 'Channel', units='(#)')
        # self._plot.setLabel('bottom', 'Wavelength' , units='nm')  # TODO Display wavelengths instead of channel number
        self._plot.setLabel('left', 'Signal', units='counts')
        # self.m_plot.setYRange(0, 5)
        self._plot.setMouseEnabled(x=False, y=True)
        self._plot.showGrid(x=True, y=True)
        self._plot.enableAutoRange(x=True, y=True)
        self._plot.getAxis('left').enableAutoSIPrefix(False)

        super().__init__(cfg_id, signal, *args, **kwargs)

        # Default serial communication parameters
        #   8 bit, no parity, 1 stop bit, no flow control
        self.default_serial_baudrate = 57600
        self.default_serial_timeout = 5
        #   frame_format: FULL_ASCII (others mode: NONE, FULL_BINARY, REDUCED_BINARY, CONCENTRATION_ASCII)

        # Auxiliary Data Plugin
        self.plugin_aux_data = True
        self.plugin_aux_data_variable_names = ['Nitrate (µM)', 'Absorbance(254)', 'Absorbance(350)',
                                               'Internal Temp. (ºC)']

        # Display only selected variables
        self.plugin_active_timeseries_variables_selected = [
            'Light Frm Nitrate', 'Light Frm abs(254)', 'Light Frm abs(350)',
            'Dark Frm Nitrate', 'Dark Frm abs(254)', 'Dark Frm abs(350)']

    def setup(self, cfg):
        # TODO Load device file to retrieve wavelength registration, 0 spectrum, and tdf
        # Overload cfg with Suna specific parameters
        cfg['variable_names'] = ['header', 'suna_date', 'suna_time',
                                 'nitrate', 'nitrogen_in_nitrate', 'absorbance_254', 'absorbance_350', 'bromide_trace',
                                 'spectrum_average', 'dark_value_used_for_fit', 'int_time_factor',
                                *[f'channel_{k}' for k in range(self.N_CHANNELS)],
                                 'int_temp', 'spec_temp', 'lamp_temp', 'lamp_time', 'rel_humid',
                                 'main_volt', 'lamp_volt', 'int_vol', 'main_current',
                                 'fit_aux1', 'fit_aux2', 'fit_base1', 'fit_base2', 'fit_rmse',
                                 'ctd_time', 'ctd_sal', 'ctd_temp', 'ctd_pres', 'checksum']
        cfg['variable_units'] = ['SAT$$$####', 'yyyyjjj', 'HH.HHHHHH',
                                 'uM', 'mgN/L', '', '', 'mg/L',
                                 'counts', '', '', *['counts'] * self.N_CHANNELS,
                                 'degC', 'degC', 'degC', 's', '%',
                                 'V', 'V', 'V', 'mA',
                                 '', '', '', '', '',
                                 's', 'PSU', 'degC', 'dBar', '']
        cfg['variable_precision'] = ['%s', '%d', '%.6f',
                                     '%.2f', '%.4f', '%.4f', '%.4f', '%.2f',
                                     '%d', '%d', '%d', *['%d'] * self.N_CHANNELS,
                                     '%.1f', '%.1f', '%.1f', '%d', '%.1f',
                                     '%.1f', '%.1f', '%.1f', '%d',
                                     '%.2f', '%.2f', '%.4f', '%.6f', '%.6f',
                                     '%.0f', '%.4f', '%.4f', '%.4f', '%d']
        cfg['variable_types'] = [str, int, float,
                                 float, float, float, float, float,
                                 int, int, int, *[int] * self.N_CHANNELS,
                                 float, float, float, int, float,
                                 float, float, float, int,
                                 float, float, float, float, float,
                                 float, float, float, float, int]
        cfg['terminator'] = b'\r\n'
        # Set standard configuration and check cfg input
        super().setup(cfg)
        # Suna Specific named tuple maker
        self.df_maker = namedtuple('SunaDataFrame', self.variable_names)
        # Update Plot config
        min_wl, max_wl = min(self.wavelength), max(self.wavelength)
        self._plot.setXRange(min_wl, max_wl)
        self._plot.setLimits(minXRange=min_wl, maxXRange=max_wl)

    def parse(self, packet):
        try:
            return self.df_maker(*[t(v) if v else float('nan') for t, v
                                   in zip(self.variable_types, packet.decode('ascii').split(','))])
        except TypeError as e:
            self.signal.packet_corrupted.emit()
            self.logger.warning(e)
            self.logger.debug(packet + self._terminator)

    def handle_data(self, raw, timestamp):
        ts_data = [raw.nitrate, raw.absorbance_254, raw.absorbance_350]
        if 'L' in raw.header:    # Light (SATSLF)
            # Update plots
            self.signal.new_data.emit(ts_data + [float('nan')] * 3, timestamp)
            self._plot_curve_light.setData(np.array(self.wavelength),
                                           np.array(raw[self.CHANNELS_START_IDX:self.CHANNELS_END_IDX]))
            # Update Auxiliary Data Plugin
            self.signal.new_aux_data.emit(['%.2f' % raw.nitrate, '%.4f' % raw.absorbance_254,
                                           '%.4f' % raw.absorbance_350, '%.1f' % raw.int_temp])
        elif 'D' in raw.header:  # Dark (SATSDF)
            # Update plots
            self.signal.new_data.emit([float('nan')] * 3 + ts_data, timestamp)
            self._plot_curve_dark.setData(self.wavelength,
                                          np.array(raw[self.CHANNELS_START_IDX:self.CHANNELS_END_IDX]))
            # Do NOT update auxiliary data
        else:
            self.logger.info(f'Unknown data frame: {raw.header}')
            return
        # Log raw data
        if self.log_prod_enabled and self._log_active:
            self._log_prod.write(list(raw), timestamp)
            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()


# class SunaParser:
#     def __init__(self, calibration_file):
#         n_channels = 256
#         self.variable_ids = ['header', 'suna_date', 'suna_time'
#                              'nitrate', 'nitrogen_in_nitrate', 'abs(254)', 'abs(350)', 'bromide_trace',
#                              'spectrum_average', 'dark_value_used_for_fit', 'int_time_factor'] +\
#                             [f'channel_{k}' for k in range(n_channels)] + \
#                             ['int_temp', 'spec_temp', 'lamp_temp', 'lamp_time', 'rel_humid',
#                              'main_volt', 'lamp_volt', 'int_vol', 'main_current',
#                              'fit_aux1', 'fit_aux2', 'fit_base1', 'fit_base2', 'fit_rmse',
#                              'ctd_time', 'ctd_sal', 'ctd_temp', 'ctd_pres']
#         self.variable_units = ['isoformat', 'uM', 'mgN/L', '', '', 'mg/L',
#                                  'counts', '', '', *['counts'] * n_channels,
#                                  'degC', 'degC', 'degC', 's', '%',
#                                  'V', 'V', 'V', 'mA',
#                                  '', '', '', '', '',
#                                  's', 'PSU', 'degC', 'dBar']
#         self.variable_precision = ['%s', '%.2f', '%.4f', '%.4f', '%.4f', '%.2f',
#                                      '%d', '%d', '%d', *['%d'] * n_channels,
#                                      '%.1f', '%.1f', '%.1f', '%d', '%.1f',
#                                      '%.1f', '%.1f', '%.1f', '%d',
#                                      '%.2f', '%.2f', '%.4f', '%.6f', '%.6f',
#                                      '%d', '%.4f', '%.4f', '%.4f']
#         self.data_frame_maker = namedtuple('SunaDataFrame', self.variable_ids)
#
#     def unpack(self, packet):
#         return self.data_frame_maker(*packet.split(','))

# default parameters:
#   serial parameters: 8 bit, no parity, 1 stop bit, no flow control
#   baudrate: 56750
#   serial_timeout: 5 s
#   frame_format: FULL_ASCII (others mode: NONE, FULL_BINARY, REDUCED_BINARY, CONCENTRATION_ASCII)

# Parameters to set (different from default)
#   set opermode continous   # Non default value
#   set operctrl samples
#   set drksmpls 1
#   set lgtsmpls 10
#   set drkavers 1
#   set lgtavers 1

# Needed:
#   tdf files from satlantic
#   reference spectrum in calibration file SNA####<A-Z>.cal or SNA####<A-Z>.CAL

