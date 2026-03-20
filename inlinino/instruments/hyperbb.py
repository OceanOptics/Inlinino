import os.path
from time import sleep

from typing import Optional
from threading import Lock

import numpy as np
from scipy.io import loadmat
from scipy.interpolate import RegularGridInterpolator, splrep, splev  # , pchip_interpolate

from inlinino.instruments import Instrument


class HyperBB(Instrument):

    REQUIRED_CFG_FIELDS = ['model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_precision']

    def __init__(self, uuid, cfg, signal, *args, **kwargs):
        super().__init__(uuid, cfg, signal, setup=False, *args, **kwargs)
        # Instrument Specific Attributes
        self._parser: Optional[HyperBBParser] = None
        self.signal_reconstructed = None
        self.invalid_packet_alarm_triggered = False
        # Default serial communication parameters
        self.default_serial_baudrate = 19200
        self.default_serial_timeout = 1
        # Init Auxiliary Data widget
        self.widget_aux_data_enabled = True
        self.widget_aux_data_variable_names = ['Scan WL. (nm)', 'Gain', 'LED Temp. (ºC)', 'Water Temp. (ºC)',
                                               'Pressure (dBar)', 'Ref Zero Flag']
        # Select Channels to Plot widget
        self.widget_select_channel_enabled = True
        self.widget_active_timeseries_variables_names = []
        self.widget_active_timeseries_variables_selected = []
        self.active_timeseries_variables_lock = Lock()
        self.active_timeseries_variables_reset = False
        self.active_timeseries_wavelength = None
        # Init Spectrum Plot widget
        self.spectrum_plot_enabled = True
        self.spectrum_plot_axis_labels = dict(y_label_name='bb', y_label_units='m<sup>-1</sup>')
        self.spectrum_plot_trace_names = ['bb']
        self.spectrum_plot_x_values = []
        # Setup
        self.setup(cfg)

    def setup(self, cfg):
        # Set HyperBB specific attributes
        if 'plaque_file' not in cfg.keys():
            raise ValueError('Missing calibration plaque file (*.mat)')
        if 'data_format' not in cfg.keys():
            cfg['data_format'] = 'advanced'
        if 'cal_format' not in cfg.keys():
            cfg['cal_format'] = 'legacy'
        temperature_file = cfg.get('temperature_file', None)
        self._parser = HyperBBParser(cfg['plaque_file'], temperature_file, cfg['data_format'],
                                     cfg['cal_format'])
        self.signal_reconstructed = np.empty(len(self._parser.wavelength)) * np.nan
        # Overload cfg with received data
        prod_var_names = ['beta_u', 'bb']
        prod_var_units = ['m-1 sr-1', 'm-1']
        prod_var_precision = ['%.5e', '%.5e']
        cfg['variable_names'] = self._parser.FRAME_VARIABLES + prod_var_names
        cfg['variable_units'] = [''] * len(self._parser.FRAME_VARIABLES) + prod_var_units
        cfg['variable_precision'] = self._parser.FRAME_PRECISIONS + prod_var_precision
        cfg['terminator'] = b'\n'
        # Set standard configuration and check cfg input
        super().setup(cfg)
        # Update wavelengths for Spectrum Plot
        self.spectrum_plot_x_values = [self._parser.wavelength]
        # Update Active Timeseries Variables
        self.widget_active_timeseries_variables_names = ['beta(%d)' % x for x in self._parser.wavelength]
        self.widget_active_timeseries_variables_selected = []
        self.active_timeseries_wavelength = np.zeros(len(self._parser.wavelength), dtype=bool)
        for wl in np.arange(450, 700, 50):
            channel_name = 'beta(%d)' % self._parser.wavelength[np.argmin(np.abs(self._parser.wavelength - wl))]
            self.update_active_timeseries_variables(channel_name, True)
        # Reset Alarm
        self.invalid_packet_alarm_triggered = False

    def parse(self, packet):
        if len(packet) == 0:  # Empty lines on firmware v2 at end of wavelength scan
            return []
        data = self._parser.parse(packet)
        if len(data) == 0:
            self.signal.packet_corrupted.emit()
            if self.invalid_packet_alarm_triggered is False:
                self.invalid_packet_alarm_triggered = True
                self.logger.warning('Unable to parse frame.')
                self.signal.alarm_custom.emit('Unable to parse frame.',
                                              'If all frames are like this, check HyperBB data format in "Setup".')
        return data

    def init_interface(self):
        self._interface.write(b'\x03')  # Send Ctrl+C to stop acquisition
        sleep(0.25)
        self._interface.write(b'savedata 0\r\n')
        sleep(0.1)
        self._interface.write(b'scan\r\n')
        sleep(0.1)
        # flush to prevent unable to parse
        self._interface.init()

    def handle_data(self, raw, timestamp):
        beta_u, bb, wl, gain, net_ref_zero_flag = self._parser.calibrate(np.array([raw], dtype=float))
        signal = np.empty(len(self._parser.wavelength)) * np.nan
        try:
            sel = self._parser.wavelength == int(wl)
            signal[sel] = bb
            self.signal_reconstructed[sel] = bb
        except ValueError:
            # Unknown wavelength
            pass
        # Update plots
        if self.active_timeseries_variables_lock.acquire(timeout=0.125):
            try:
                self.signal.new_ts_data[object, float, bool].emit(signal[self.active_timeseries_wavelength], timestamp,
                                                                  self.active_timeseries_variables_reset)
                self.active_timeseries_variables_reset = False  # Reset here as potentially set by update_active_timeseries_variables
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update timeseries plot')
        gain = 'High' if gain == 3 else 'Low' if gain == 2 else 'None'
        self.signal.new_aux_data.emit([int(wl), gain, raw[self._parser.idx_LedTemp],
                                       raw[self._parser.idx_WaterTemp], raw[self._parser.idx_Depth],
                                       net_ref_zero_flag])
        self.signal.new_spectrum_data.emit([self.signal_reconstructed])
        # Log data as received
        if self.log_prod_enabled and self._log_active:
            self._log_prod.write(np.concatenate((raw, beta_u, bb)), timestamp)
            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()

    def update_active_timeseries_variables(self, name, state):
        if not ((state and name not in self.widget_active_timeseries_variables_selected) or
                (not state and name in self.widget_active_timeseries_variables_selected)):
            return
        if self.active_timeseries_variables_lock.acquire(timeout=0.125):
            self.active_timeseries_variables_reset = True
            try:
                index = self.widget_active_timeseries_variables_names.index(name)
                self.active_timeseries_wavelength[index] = state
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update active timeseries variables')
        # Update list of active variables for GUI keeping the order
        self.widget_active_timeseries_variables_selected = \
            ['beta(%d)' % wl for wl in self._parser.wavelength[self.active_timeseries_wavelength]]


LEGACY_DATA_FORMAT = 0
ADVANCED_DATA_FORMAT = 1
LIGHT_DATA_FORMAT = 2

class HyperBBParser():
    def __init__(self, plaque_cal_file, temperature_cal_file=None, data_format='advanced', cal_format='legacy'):
        # Frame Parser
        if data_format.lower() == 'legacy':
            self.data_format = LEGACY_DATA_FORMAT
        elif data_format.lower() == 'advanced':
            self.data_format = ADVANCED_DATA_FORMAT
        elif data_format.lower() == 'light':
            self.data_format = LIGHT_DATA_FORMAT
        else:
            raise ValueError('Data format not recognized.')
        if self.data_format == LEGACY_DATA_FORMAT:  # Manual version 1.2
            self.FRAME_VARIABLES = ['ScanIdx', 'DataIdx', 'Date', 'Time', 'StepPos', 'wl', 'LedPwr', 'PmtGain',
                                    'NetSig1', 'SigOn1', 'SigOn1Std', 'RefOn', 'RefOnStd', 'SigOff1', 'SigOff1Std',
                                    'RefOff', 'RefOffStd', 'SigOn2', 'SigOn2Std', 'SigOn3', 'SigOn3Std', 'SigOff2',
                                    'SigOff2Std', 'SigOff3', 'SigOff3Std', 'LedTemp', 'WaterTemp',
                                    'Depth', 'Saturation', 'CalPlaqueDist']
            # Channel "Saturation" might be "Debug1" depending on firmware version
            self.FRAME_TYPES = [int, int, str, str, int, int, int, int, int,
                               float, float, float, float, float, float, float,
                               float, float, float, float, float, float, float,
                               float, float, float, float, float, int, int]
            # FRAME_PRECISIONS = ['%d', '%d', '%s', '%s', '%d', '%d', '%d', '%d', '%d',
            #                    '%.1f', '%.1f', '%.1f', '%.1f', '%.1f', '%.1f', '%.1f',
            #                    '%.1f', '%.1f', '%.1f', '%.1f', '%.1f', '%.1f', '%.1f',
            #                    '%.1f', '%.1f', '%.2f', '%.2f', '%.2f', '%d', '%d']
            self.FRAME_PRECISIONS = ['%s'] * len(self.FRAME_VARIABLES)
            for x in self.FRAME_VARIABLES:
                setattr(self, f'idx_{x}', self.FRAME_VARIABLES.index(x))
        elif self.data_format == ADVANCED_DATA_FORMAT:  # Firmware version >= 1.68 or Manual version 1.3
            # The advanced output contains extra parameters:
            #     - The standard deviation can be used as a proxy for particle size.
            #     - The stepper position can be used to determine wavelength registration in case of instrument issues.
            self.FRAME_VARIABLES = ['ScanIdx', 'DataIdx', 'Date', 'Time', 'StepPos', 'wl', 'LedPwr', 'PmtGain',
                                    'NetSig1', 'SigOn1', 'SigOn1Std', 'RefOn', 'RefOnStd', 'SigOff1', 'SigOff1Std',
                                    'RefOff', 'RefOffStd', 'SigOn2', 'SigOn2Std', 'SigOn3', 'SigOn3Std',
                                    'SigOff2', 'SigOff2Std', 'SigOff3', 'SigOff3Std', 'LedTemp', 'WaterTemp',
                                    'Depth', 'SupplyVolt', 'Saturation', 'CalPlaqueDist']
            self.FRAME_TYPES = [int, int, str, str, int, int, int, int, int,
                                float, float, float, float, float, float, float,
                                float, float, float, float, float, float, float,
                                float, float, float, float, float, float, int, int]
            self.FRAME_PRECISIONS = ['%s'] * len(self.FRAME_VARIABLES)
            for x in self.FRAME_VARIABLES:
                setattr(self, f'idx_{x}', self.FRAME_VARIABLES.index(x))
        elif self.data_format == LIGHT_DATA_FORMAT:
            self.FRAME_VARIABLES = ['ScanIdx', 'Date', 'Time', 'wl', 'PmtGain',
                                    'NetRef', 'NetSig1', 'NetSig2', 'NetSig3',
                                    'LedTemp', 'WaterTemp', 'Depth', 'SupplyVolt', 'ChSaturated']
            self.FRAME_TYPES = [int, str, str, int, int,
                                float, float, float, float, float,
                                float, float, float, float, int]
            self.FRAME_PRECISIONS = ['%s'] * len(self.FRAME_VARIABLES)
            for x in self.FRAME_VARIABLES:
                setattr(self, f'idx_{x}', self.FRAME_VARIABLES.index(x))
        else:
            raise ValueError('Firmware version not supported.')

        # Instrument Specific Attributes
        self._theta = float('nan')
        self.Xp = float('nan')

        # Calibration Parameters
        self.remove_scans_multiple_gain = False
        self.saturation_level = 4000
        self.theta = 135  # calls theta setter which sets Xp

        # Load calibration files (supports legacy two-file format and current single-file format)
        p_cal, t_cal = self._load_calibration(plaque_cal_file, temperature_cal_file, cal_format)

        self.wavelength = t_cal['wl']
        self.cal_t_coef = t_cal['coeff']
        self.pmt_ref_gain = p_cal['pmtRefGain']
        self.pmt_gamma = p_cal['pmtGamma']
        self.gain12 = p_cal['gain12']
        self.gain23 = p_cal['gain23']

        # Check wavelength match in all calibration files
        if np.any(p_cal['darkCalWavelength'] != p_cal['muWavelengths']) or \
                np.any(p_cal['darkCalWavelength'] != t_cal['wl']):
            raise ValueError('Wavelength from calibration files don\'t match.')

        # Pre-compute temperature correction grid over an extensive temperature range.
        # The grid spans 0–50°C, covering the full operational range of the LED.
        # RegularGridInterpolator uses fill_value=None which extrapolates beyond the grid
        # edges; log a warning if data temperatures fall outside this range.
        _led_t_grid = np.arange(0, 50.01, 0.1)
        _t_corr_grid = np.empty((len(self.wavelength), len(_led_t_grid)))
        for k in range(len(self.wavelength)):
            _t_corr_grid[k, :] = np.polyval(self.cal_t_coef[k, :], _led_t_grid)
        self._f_t_correction = RegularGridInterpolator(
            (self.wavelength.astype(float), _led_t_grid),
            _t_corr_grid, method='linear', bounds_error=False, fill_value=None)

        # Prepare interpolation tables for dark offsets
        _gain_vals = p_cal['darkCalPmtGain'].astype(float)
        _wl_vals = p_cal['darkCalWavelength'].astype(float)
        self.f_dark_cal_scat_1 = RegularGridInterpolator(
            (_wl_vals, _gain_vals), p_cal['darkCalScat1'],
            method='linear', bounds_error=False, fill_value=None)
        self.f_dark_cal_scat_2 = RegularGridInterpolator(
            (_wl_vals, _gain_vals), p_cal['darkCalScat2'],
            method='linear', bounds_error=False, fill_value=None)
        self.f_dark_cal_scat_3 = RegularGridInterpolator(
            (_wl_vals, _gain_vals), p_cal['darkCalScat3'],
            method='linear', bounds_error=False, fill_value=None)
        # mu calibration corrected for temperature
        self.mu = p_cal['muFactors'] * self.compute_temperature_coefficients(p_cal['muWavelengths'],
                                                                              p_cal['muLedTemp'])

    @staticmethod
    def _load_calibration(plaque_cal_file, temperature_cal_file=None, cal_format='legacy'):
        """Load calibration data from legacy (.mat) or current binary format.

        Legacy format: Two separate .mat files — a plaque calibration file (containing a 'cal'
        struct) and a temperature calibration file (containing a 'cal_temp' struct).

        Current format: Binary plaque calibration file (.hbb_cal) and binary temperature
        calibration file (.hbb_tcal) as produced by Hbb_ConvertCalibrations.m (Sequoia, 2024).
        Both files are required for live data temperature correction.

        :param plaque_cal_file: Path to plaque .mat file (legacy) or .hbb_cal binary file (current).
        :param temperature_cal_file: Path to temperature .mat file (legacy) or .hbb_tcal binary
            file (current). Required for both calibration formats.
        :param cal_format: 'legacy' for MATLAB .mat file pair, 'current' for binary .hbb_cal/.hbb_tcal.
        :return: Tuple (p_cal, t_cal) where p_cal and t_cal are dicts of calibration parameters.
        :raises ValueError: If required files are missing or the file format is unexpected.
        """
        if cal_format == 'legacy':
            p_mat = loadmat(plaque_cal_file, simplify_cells=True)
            if 'cal' not in p_mat:
                raise ValueError(
                    f"Plaque calibration file '{plaque_cal_file}' does not contain 'cal' struct. "
                    "Ensure the correct legacy format plaque file is specified.")
            p_cal = p_mat['cal']
            if temperature_cal_file is None:
                raise ValueError(
                    'Missing temperature calibration file (*.mat). '
                    'The legacy calibration format requires two separate files.')
            t_mat = loadmat(temperature_cal_file, simplify_cells=True)
            if 'cal_temp' not in t_mat:
                raise ValueError(
                    f"Temperature calibration file '{temperature_cal_file}' does not contain "
                    "'cal_temp' struct. Check that the correct file is specified.")
            t_cal = t_mat['cal_temp']
        elif cal_format == 'current':
            if temperature_cal_file is None:
                raise ValueError(
                    'Missing temperature calibration file (*.hbb_tcal). '
                    'The current calibration format requires both a plaque (.hbb_cal) '
                    'and a temperature (.hbb_tcal) calibration file.')
            p_cal = HyperBBParser._read_binary_plaque_cal(plaque_cal_file)
            t_cal = HyperBBParser._read_binary_temp_cal(temperature_cal_file)
        else:
            raise ValueError(
                f"Calibration format '{cal_format}' not recognized. Use 'legacy' or 'current'.")
        return p_cal, t_cal

    @staticmethod
    def _read_binary_plaque_cal(filename):
        """Read a HyperBB binary plaque calibration file (.hbb_cal) as produced by
        Hbb_ConvertCalibrations.m (Sequoia Scientific, 2024).

        The file may contain multiple calibration records appended sequentially; the last
        (most recent) record is returned, consistent with MATLAB's ``cal = cal(end)``.

        Returns a dict with the same field names as the legacy .mat 'cal' struct so the rest
        of the calibration pipeline requires no changes.
        """
        records = []
        with open(filename, 'rb') as fid:
            fid.seek(0, 2)
            eof = fid.tell()
            fid.seek(0)
            while fid.tell() < eof:
                fid.read(24)   # ID string (24 chars, e.g. 'Sequoia Hyper-bb Cal')
                fid.read(2)    # calLengthBytes (uint16) — read but not needed for seeking
                fid.read(2)    # processingVersion (uint16 / 100)
                fid.read(2)    # serialNumber (uint16)
                fid.read(6)    # cal date  (6 × uint8: year-1900, month, day, hour, min, sec)
                fid.read(6)    # tempCalDate
                pmt_ref_gain = int(np.frombuffer(fid.read(2), dtype='<u2')[0])
                pmt_gamma    = float(np.frombuffer(fid.read(4), dtype='<f4')[0])
                fid.read(4)    # PMTGammaRMSE (float)
                gain12 = np.frombuffer(fid.read(2), dtype='<u2')[0] / 1000.0
                fid.read(4)    # gain1_2_std (float)
                gain23 = np.frombuffer(fid.read(2), dtype='<u2')[0] / 1000.0
                fid.read(4)    # gain2_3_std (float)
                fid.read(2)    # muFactorPMTGain (uint16)
                fid.read(2)    # transmitReceiveDistance (uint16 / 100)
                fid.read(1)    # plaqueReflectivity (uint8 / 100)
                num_mu_wl     = int(np.frombuffer(fid.read(1), dtype='<u1')[0])
                num_dark_wl   = int(np.frombuffer(fid.read(1), dtype='<u1')[0])
                num_dark_gain = int(np.frombuffer(fid.read(1), dtype='<u1')[0])
                mu_wl       = np.frombuffer(fid.read(num_mu_wl * 2),   dtype='<u2').astype(float) / 10.0
                mu_factors  = np.frombuffer(fid.read(num_mu_wl * 4),   dtype='<f4').copy()
                fid.read(num_mu_wl * 4)  # muFactorTempCorr — stored but not used in live processing
                mu_led_temp = np.frombuffer(fid.read(num_mu_wl * 2),   dtype='<u2').astype(float) / 100.0
                dark_wl     = np.frombuffer(fid.read(num_dark_wl * 2), dtype='<u2').astype(float) / 10.0
                dark_gain   = np.frombuffer(fid.read(num_dark_gain * 2), dtype='<u2').copy()
                n = num_dark_wl * num_dark_gain
                # MATLAB writes 2-D arrays column-major; Fortran order matches reshape behavior
                dark_scat1 = np.frombuffer(fid.read(n * 4), dtype='<f4').copy().reshape(
                    (num_dark_wl, num_dark_gain), order='F')
                dark_scat2 = np.frombuffer(fid.read(n * 4), dtype='<f4').copy().reshape(
                    (num_dark_wl, num_dark_gain), order='F')
                dark_scat3 = np.frombuffer(fid.read(n * 4), dtype='<f4').copy().reshape(
                    (num_dark_wl, num_dark_gain), order='F')
                records.append({
                    'pmtRefGain':        pmt_ref_gain,
                    'pmtGamma':          pmt_gamma,
                    'gain12':            float(gain12),
                    'gain23':            float(gain23),
                    'darkCalWavelength': dark_wl,
                    'darkCalPmtGain':    dark_gain,
                    'darkCalScat1':      dark_scat1,
                    'darkCalScat2':      dark_scat2,
                    'darkCalScat3':      dark_scat3,
                    'muWavelengths':     mu_wl,
                    'muFactors':         mu_factors,
                    'muLedTemp':         mu_led_temp,
                })
        if not records:
            raise ValueError(f"No valid calibration records found in '{filename}'.")
        return records[-1]  # last record, consistent with MATLAB: cal = cal(end)

    @staticmethod
    def _read_binary_temp_cal(filename):
        """Read a HyperBB binary temperature calibration file (.hbb_tcal) as produced by
        Hbb_ConvertCalibrations.m (Sequoia Scientific, 2024).

        Returns a dict with 'wl' and 'coeff' keys compatible with the legacy .mat 'cal_temp'
        struct so the temperature correction code requires no changes.
        """
        with open(filename, 'rb') as fid:
            fid.read(24)   # ID string (24 chars, e.g. 'Sequoia Hyper-bb T Cal')
            fid.read(2)    # processingVersion (uint16 / 100)
            fid.read(2)    # serialNumber (uint16)
            fid.read(6)    # date (6 × uint8: year-1900, month, day, hour, min, sec)
            fid.read(2)    # normalizedTemp (uint16 / 100)
            polynomial_order = int(np.frombuffer(fid.read(1), dtype='<u1')[0])
            num_wl           = int(np.frombuffer(fid.read(1), dtype='<u1')[0])
            wl = np.frombuffer(fid.read(num_wl * 2), dtype='<u2').astype(float) / 10.0
            # Coefficients written column-major by MATLAB (numWLs × (order+1) matrix)
            num_coeffs = num_wl * (polynomial_order + 1)
            coeffs_raw = np.frombuffer(fid.read(num_coeffs * 4), dtype='<f4').copy()
            coeff = coeffs_raw.reshape((num_wl, polynomial_order + 1), order='F')
        return {'wl': wl, 'coeff': coeff}

    @property
    def theta(self) -> float:
        return self._theta

    @theta.setter
    def theta(self, value) -> None:
        self._theta = value
        # Compute Xp with values from Sullivan et al 2013
        theta_ref = np.arange(90, 171, 10)
        Xp_ref = np.array([0.684, 0.858, 1.000, 1.097, 1.153, 1.167, 1.156, 1.131, 1.093])
        self.Xp = float(splev(self.theta, splrep(theta_ref, Xp_ref)))

    def compute_temperature_coefficients(self, wl, t):
        wl_arr = np.atleast_1d(np.asarray(wl, dtype=float))
        t_arr = np.atleast_1d(np.asarray(t, dtype=float))
        return self._f_t_correction(np.column_stack([wl_arr, t_arr]))

    def parse(self, raw):
        tmp = raw.decode().split()
        n = len(self.FRAME_VARIABLES)
        if len(tmp) != n:
            return []
        data = [None] * n
        for k, (v, t) in enumerate(zip(tmp, self.FRAME_TYPES)):
            data[k] = t(v) if t != str else float('nan')
        return data

    def calibrate(self, raw):
        """
        Calibrate an array of frames from HyperBB

        :param raw: <nx30 np.ndarray> frames decoded from HyperBB
        :return: beta: <nx28 np.ndarray> m being the number of wavelength
                 wl: <nx1 np.ndarray> wavelength (nm)
                 gain: <nx1 np.ndarray> gain used (1: none, 2: low, and 3: high)
        """

        # Remove scans with multiple gains
        if self.remove_scans_multiple_gain:
            for scan_idx in np.unique(raw[:,self.idx_ScanIdx]):
                sel = raw[:, self.idx_ScanIdx] == scan_idx
                if len(np.unique(raw[sel, self.idx_PmtGain])) > 1:
                    raw = np.delete(raw, sel, axis=0)
        # Shortcuts
        wl = raw[:, self.idx_wl]
        if self.data_format == ADVANCED_DATA_FORMAT or self.data_format == LEGACY_DATA_FORMAT:
            # Remove saturated reading
            raw[raw[:, self.idx_SigOn1] > self.saturation_level, self.idx_SigOn1] = np.nan
            raw[raw[:, self.idx_SigOn2] > self.saturation_level, self.idx_SigOn2] = np.nan
            raw[raw[:, self.idx_SigOn3] > self.saturation_level, self.idx_SigOn3] = np.nan
            raw[raw[:, self.idx_SigOff1] > self.saturation_level, self.idx_SigOff1] = np.nan
            raw[raw[:, self.idx_SigOff2] > self.saturation_level, self.idx_SigOff2] = np.nan
            raw[raw[:, self.idx_SigOff3] > self.saturation_level, self.idx_SigOff3] = np.nan
            # Calculate net signal for ref, low gain (2), high gain (3)
            net_ref = raw[:, self.idx_RefOn] - raw[:, self.idx_RefOff]
            net_sig2 = raw[:, self.idx_SigOn2] - raw[:, self.idx_SigOff2]
            net_sig3 = raw[:, self.idx_SigOn3] - raw[:, self.idx_SigOff3]
            net_ref_zero_flag = np.any(net_ref == 0)
            net_ref[net_ref == 0] = np.nan
            scat1 = raw[:, self.idx_NetSig1] / net_ref
            scat2 = net_sig2 / net_ref
            scat3 = net_sig3 / net_ref
            # Keep gain setting
            gain = np.ones((len(raw), 1)) * 3
            gain[np.isnan(raw[:, self.idx_SigOn3])] = 2
            gain[np.isnan(raw[:, self.idx_SigOn2])] = 1
            gain[np.isnan(raw[:, self.idx_SigOn1])] = 0  # All signals saturated
        else:  # Light Format
            net_ref_zero_flag = np.any(raw[:, self.idx_NetRef] == 0)
            raw[raw[:, self.idx_ChSaturated] == 1, self.idx_NetSig1] = np.nan
            raw[(0 < raw[:, self.idx_ChSaturated]) & (raw[:, self.idx_ChSaturated] <= 2), self.idx_NetSig2] = np.nan
            raw[(0 < raw[:, self.idx_ChSaturated]) & (raw[:, self.idx_ChSaturated] <= 3), self.idx_NetSig3] = np.nan
            scat1 = raw[:, self.idx_NetSig1] / raw[:, self.idx_NetRef]
            scat2 = raw[:, self.idx_NetSig2] / raw[:, self.idx_NetRef]
            scat3 = raw[:, self.idx_NetSig3] / raw[:, self.idx_NetRef]
            # Keep Gain setting
            gain = np.ones((len(raw), 1)) * 3
            gain[raw[:, self.idx_ChSaturated] == 3] = 2
            gain[raw[:, self.idx_ChSaturated] == 2] = 1
            gain[raw[:, self.idx_ChSaturated] == 1] = 0  # All signals saturated
        # Subtract dark offset
        _pts = np.column_stack([wl, raw[:, self.idx_PmtGain]])
        scat1_dark_removed = scat1 - self.f_dark_cal_scat_1(_pts)
        scat2_dark_removed = scat2 - self.f_dark_cal_scat_2(_pts)
        scat3_dark_removed = scat3 - self.f_dark_cal_scat_3(_pts)
        # Apply PMT and front end gain factors
        g_pmt = (raw[:, self.idx_PmtGain] / self.pmt_ref_gain) ** self.pmt_gamma
        scat1_gain_corrected = scat1_dark_removed * self.gain12 * self.gain23 * g_pmt
        scat2_gain_corrected = scat2_dark_removed * self.gain23 * g_pmt
        scat3_gain_corrected = scat3_dark_removed * g_pmt
        # Apply temperature Correction
        t_correction = self.compute_temperature_coefficients(wl, raw[:, self.idx_LedTemp])
        scat1_t_corrected = scat1_gain_corrected * t_correction
        scat2_t_corrected = scat2_gain_corrected * t_correction
        scat3_t_corrected = scat3_gain_corrected * t_correction
        # Select highest non-saturated gain channel
        scatx_corrected = scat3_t_corrected  # default is high gain
        scatx_corrected[np.isnan(scatx_corrected)] = scat2_t_corrected[np.isnan(scatx_corrected)] # otherwise low gain
        scatx_corrected[np.isnan(scatx_corrected)] = scat1_t_corrected[np.isnan(scatx_corrected)] # otherwise raw pmt
        # Calculate beta
        uwl = np.unique(wl)
        # mu = pchip_interpolate(self.wavelength, self.mu, uwl)  # Optimized as no need of interpolation as same wavelength as calibration
        beta_u = np.empty(len(raw))
        # for k, w in enumerate(uwl):
        for kwl in uwl:
            beta_u[wl == kwl] = scatx_corrected[wl == kwl] * self.mu[self.wavelength == kwl]
        # Calculate backscattering
        bb = 2 * np.pi * self.Xp * beta_u
        return beta_u, bb, wl, gain, net_ref_zero_flag


if __name__ == "__main__":
    import os
    p_cal = os.path.join('..', 'cfg', 'HBB8005_CalPlaque_20210315.mat')
    t_cal = os.path.join('..', 'cfg', 'HBB8005_CalTemp_20210315.mat')

    hbb = HyperBBParser(p_cal, t_cal)
