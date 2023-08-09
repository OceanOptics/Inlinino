from collections import namedtuple

from inlinino.instruments import Instrument
import numpy as np


class SunaV2(Instrument):
    REQUIRED_CFG_FIELDS = ['calibration_file',
                           'model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_precision']
    N_CHANNELS = 256
    CHANNELS_START_IDX = 11
    CHANNELS_END_IDX = CHANNELS_START_IDX + N_CHANNELS
    VARIABLE_NAMES = ['header', 'suna_date', 'suna_time',
                      'nitrate', 'nitrogen_in_nitrate', 'absorbance_254', 'absorbance_350', 'bromide_trace',
                      'spectrum_average', 'dark_value_used_for_fit', 'int_time_factor',
                     # *[f'uv_{wl:.2f}' for wl in self.wavelength],  # Need valid identifier
                      *[f'channel_{k}' for k in range(N_CHANNELS)],
                      'int_temp', 'spec_temp', 'lamp_temp', 'lamp_time', 'rel_humid',
                      'main_volt', 'lamp_volt', 'int_volt', 'main_current',
                      'fit_aux1', 'fit_aux2', 'fit_base1', 'fit_base2', 'fit_rmse',
                      'ctd_time', 'ctd_sal', 'ctd_temp', 'ctd_pres', 'checksum']
    VARIABLE_UNITS = ['SAT$$$####', 'yyyyjjj', 'HH.HHHHHH',
                      'uM', 'mgN/L', '', '', 'mg/L',
                      'counts', '', '', *['counts'] * N_CHANNELS,
                      'degC', 'degC', 'degC', 's', '%',
                      'V', 'V', 'V', 'mA',
                      '', '', '', '', '',
                      's', 'PSU', 'degC', 'dBar', '']
    VARIABLE_PRECISION = ['%s', '%d', '%.6f',
                          '%.2f', '%.4f', '%.4f', '%.4f', '%.2f',
                          '%d', '%d', '%d', *['%d'] * N_CHANNELS,
                          '%.1f', '%.1f', '%.1f', '%d', '%.1f',
                          '%.1f', '%.1f', '%.1f', '%d',
                          '%.2f', '%.2f', '%.4f', '%.6f', '%.6f',
                          '%.0f', '%.4f', '%.4f', '%.4f', '%d']
    VARIABLE_TYPES = [str, int, float,
                      float, float, float, float, float,
                      int, int, int, *[int] * N_CHANNELS,
                      float, float, float, int, float,
                      float, float, float, int,
                      float, float, float, float, float,
                      float, float, float, float, int]

    def __init__(self, uuid, cfg, signal, *args, **kwargs):
        super().__init__(uuid, cfg, signal, setup=False, *args, **kwargs)
        # Suna Specific Attributes
        self.df_maker = None
        self.wavelength = np.array([c for c in range(self.N_CHANNELS)])
        # Default serial communication parameters
        #   8 bit, no parity, 1 stop bit, no flow control
        self.default_serial_baudrate = 57600
        self.default_serial_timeout = 5
        #   frame_format: FULL_ASCII (others mode: NONE, FULL_BINARY, REDUCED_BINARY, CONCENTRATION_ASCII)
        # Auxiliary Data widget
        self.widget_aux_data_enabled = True
        self.widget_aux_data_variable_names = self.get_aux_names()
        # Display only selected variables
        self.widget_active_timeseries_variables_selected = self.get_ts_names()
        # Init Spectrum Plot widget
        self.spectrum_plot_enabled = True
        self.spectrum_plot_axis_labels = dict(x_label_name='Channel', x_label_units='(#)',
                                              y_label_name='Signal', y_label_units='counts')
        self.spectrum_plot_trace_names = ['light', 'dark']
        self.spectrum_plot_x_values = [self.wavelength, self.wavelength]
        # Setup
        self.setup(cfg)

    def setup(self, cfg):
        # TODO Load device file to retrieve wavelength registration, 0 spectrum, and tdf
        # Set ACS specific attributes
        if 'calibration_file' not in cfg.keys():
            raise ValueError('Missing field calibration file')
        self.register_wavelengths(cfg['calibration_file'])  # Which updates spectrum plots parameters
        # Overload cfg with Suna specific parameters
        cfg['variable_names'] = self.VARIABLE_NAMES
        cfg['variable_units'] = self.VARIABLE_UNITS
        cfg['variable_precision'] = self.VARIABLE_PRECISION
        cfg['variable_types'] = self.VARIABLE_TYPES
        cfg['terminator'] = b'\r\n'
        # Set standard configuration and check cfg input
        super().setup(cfg)
        # Suna Specific named tuple maker
        self.df_maker = namedtuple('SunaDataFrame', self.variable_names)

    def register_wavelengths(self, calibration_filename):
        # Read polynomial coefficients for wavelength calculation from pixel value
        try:
            c = [0.] * 5
            with open(calibration_filename, 'r') as f:
                for l in f:
                    if l[:2] == '/*':  # Comment
                        continue
                    elif l[0] == 'C':
                        c[int(l[1])] = float(l.split(' ')[1])
            x = np.arange(1, self.N_CHANNELS+1)
            self.wavelength = c[0] + c[1] * x + c[2] * x**2 + c[3] * x**3 + c[4] * x**4
            self.spectrum_plot_axis_labels['x_label_name'] = 'Wavelength'
            self.spectrum_plot_axis_labels['x_label_units'] = 'nm'
        except:
            self.logger.warning('Error registering wavelengths.')
        if not np.all(np.diff(self.wavelength)):  # some wavelengths are identical
            self.logger.warning('Invalid wavelength registration.')
            self.wavelength = np.array([c for c in range(self.N_CHANNELS)])
            self.spectrum_plot_axis_labels['x_label_name'] = 'Channel'
            self.spectrum_plot_axis_labels['x_label_units'] = '#'
        self.spectrum_plot_x_values = [self.wavelength, self.wavelength]

    def parse(self, packet):
        try:
            return self.df_maker(*[t(v) if v else float('nan') for t, v
                                   in zip(self.variable_types, packet.decode('ascii').split(','))])
        except TypeError as e:
            self.signal.packet_corrupted.emit()
            self.logger.warning(e)
            self.logger.debug(packet + self._terminator)

    def handle_data(self, raw, timestamp):
        if 'L' in raw.header:    # Light (SATSLF)
            # Update plots
            self.signal.new_ts_data.emit(self.get_ts(raw), timestamp)
            self.signal.new_spectrum_data.emit([np.array(raw[self.CHANNELS_START_IDX:self.CHANNELS_END_IDX]), None])
            # Update Auxiliary Data widget
            self.signal.new_aux_data.emit(self.get_aux(raw))
        elif 'D' in raw.header:  # Dark (SATSDF)
            # Update spectrum plot
            self.signal.new_spectrum_data.emit([None, np.array(raw[self.CHANNELS_START_IDX:self.CHANNELS_END_IDX])])
            # Do NOT update auxiliary data
        else:
            self.logger.info(f'Unknown data frame: {raw.header}')
            return
        # Log raw data
        if self.log_prod_enabled and self._log_active:
            self._log_prod.write(list(raw), timestamp)
            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()

    def get_ts(self, raw):
        return [raw.nitrate, raw.absorbance_254, raw.absorbance_350]

    def get_ts_names(self):
        return ['Nitrate (µM)', 'A(254) (Au)', 'A(350) (Au)']

    @staticmethod
    def get_aux(raw):
        return ['%.2f' % raw.nitrate, '%.4f' % raw.absorbance_254, '%.4f' % raw.absorbance_350, '%.1f' % raw.int_temp]

    @staticmethod
    def get_aux_names():
        return ['Nitrate (µM)', 'Absorbance(254) (Au)', 'Absorbance(350) (Au)', 'Internal Temp. (ºC)']


class SunaV1(SunaV2):
    N_CHANNELS = 226
    CHANNELS_START_IDX = 14
    CHANNELS_END_IDX = CHANNELS_START_IDX + N_CHANNELS
    VARIABLE_NAMES = ['header', 'suna_timestamp',
                      'nitrate', 'nitrogen_in_nitrate', 'fit_rmse',
                      'lamp_temp', 'spec_temp', 'lamp_time', 'rel_humid',
                      'lamp_volt', 'reg_volt', 'main_volt',
                      'spectrum_average', 'dark_average',
                      # *[f'uv_{wl:.2f}' for wl in self.wavelength],  # Need valid identifier
                      *[f'channel_{k}' for k in range(N_CHANNELS)],
                      'checksum']
    VARIABLE_UNITS = ['SAT$$$####', 'seconds',
                      'uMolar', 'mgN/L', '',
                      'degC', 'degC', 's', '%',
                      'V', 'V', 'V',
                      '', '',
                      *['counts'] * N_CHANNELS,
                      '']
    VARIABLE_PRECISION = ['%s', '%.3f',
                          '%.2f', '%.4f', '%.6f',
                          '%.3f', '%.3f', '%d', '%.1f',
                          '%.2f', '%.2f', '%.2f',
                          '%d', '%d',
                          *['%d'] * N_CHANNELS,
                          '%d']
    VARIABLE_TYPES = [str, float,
                      float, float, float,
                      float, float, int, float,
                      float, float, float,
                      int, int,
                      *[int] * N_CHANNELS,
                      int]

    def __init__(self, uuid, signal, *args, **kwargs):
        super().__init__(uuid, signal, *args, **kwargs)
        # Default serial communication parameters different from V2
        self.default_serial_baudrate = 38400

    def get_ts(self, raw):
        idx254 = np.argmin(np.abs(self.wavelength - 254))
        idx350 = np.argmin(np.abs(self.wavelength - 350))
        return [raw.nitrate, raw.__getattribute__(f'channel_{idx254}'), raw.__getattribute__(f'channel_{idx350}')]

    def get_ts_names(self):
        return ['Nitrate (µM)', 'A(254) (counts)', 'A(350) (counts)']

    @staticmethod
    def get_aux(raw):
        return ['%.2f' % raw.nitrate, '%.2f' % raw.lamp_temp, '%.2f' % raw.spec_temp]

    @staticmethod
    def get_aux_names():
        return ['Nitrate (µM)', 'Lamp Temp. (ºC)', 'Spec Temp. (ºC)']


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
#   set drksmpls 1           # Set at 2 on Suna 1504
#   set lgtsmpls 10          # Set at 58 on Suna 1504
#   set drkavers 1
#   set lgtavers 1

# Needed:
#   tdf files from satlantic
#   reference spectrum in calibration file SNA####<A-Z>.cal or SNA####<A-Z>.CAL

