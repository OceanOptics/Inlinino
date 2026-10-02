from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from time import sleep
from threading import Lock
from typing import Optional, Type, Union, Tuple

import numpy as np
from numpy.typing import NDArray
from scipy.io import loadmat
from scipy.interpolate import interp2d, splrep, splev, pchip_interpolate

from inlinino.instruments import Instrument
from inlinino.widgets import classproperty


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
            raise ValueError('Missing calibration plaque file (*.mat or *.hbb_cal)')
        if not str(cfg['plaque_file']).lower().endswith('.hbb_cal') and not cfg.get('temperature_file'):
            raise ValueError('Missing calibration temperature file (*.mat or *.hbb_tcal)')
        if 'data_format' not in cfg.keys():
            cfg['data_format'] = 'auto'
        self._parser = HyperBBParser(cfg['plaque_file'], cfg.get('temperature_file', ''), cfg['data_format'])
        # Check serial number is consistent
        cal = self._parser.p_cal
        configured_serial = str(cfg.get('serial_number', '')).strip()
        if configured_serial and cal.serial_number and configured_serial != str(cal.serial_number):
            raise ValueError('HyperBB serial number in calibration file %d does not match instrument setup %d.'
                             % (cal.serial_number, configured_serial))
        self.signal_reconstructed = np.empty(len(self._parser.wavelength)) * np.nan
        # Overload cfg with received data
        cfg.update(self.get_variables_from_data_format())
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

    def get_variables_from_data_format(self):
        prod_var_names = ('beta_u', 'bb')
        prod_var_units = ['m-1 sr-1', 'm-1']
        prod_var_precision = ['%.5e', '%.5e']
        if self._parser.data_format is None:
            self.variable_names = prod_var_names
            self.variable_units = prod_var_units
            variable_precision = prod_var_precision
        else:
            self.variable_names = self._parser.data_format.FRAME_VARIABLES + prod_var_names
            self.variable_units = [''] * len(self._parser.data_format.FRAME_VARIABLES) + prod_var_units
            variable_precision = self._parser.data_format.FRAME_PRECISIONS + prod_var_precision
        return {
            'variable_names': self.variable_names,
            'variable_units': self.variable_units,
            'variable_precision': variable_precision,
        }

    def parse(self, packet):
        if not packet.strip():  # Empty lines on firmware v2 at end of wavelength scan
            return []
        data, updated_format = self._parser.parse(packet)
        if updated_format:
            self._log_prod.update_cfg(self.get_variables_from_data_format())
            self.logger.info('HyperBB data format updated to "%s"', self._parser.data_format.name)
            self.signal.alarm_custom.emit('HyperBB data format updated to "%s"' % self._parser.data_format.name,
                                          'This messages appeared because data format is set to "auto" in "Setup". '
                                          'If this is incorrect, change data format in "Setup".')

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
        # Reset Alarm
        self.invalid_packet_alarm_triggered = False

    def handle_data(self, raw, timestamp):
        # Standardize and calibrate data
        try:
            standardized_frame = self._parser.data_format.standardize(raw)
            beta_u, bb, wl, gain, net_ref_zero_flag = self._parser.calibrate(standardized_frame)
        except HyperBBError as e:
            if self.invalid_packet_alarm_triggered is False:
                self.invalid_packet_alarm_triggered = True
                self.logger.warning('Unable to calibrate frame: %s', str(e))
                self.signal.alarm_custom.emit('Unable to calibrate frame.', str(e))
            beta_u, bb = [np.nan], [np.nan]
            self.signal.packet_corrupted.emit()  # Packet is not truly corrupted, but information is missing to calibrate it
            return
        finally:
            # Log data as received
            if self.log_prod_enabled and self._log_active:
                self._log_prod.write(raw + (beta_u[0], bb[0]), timestamp)
                if not self.log_raw_enabled:
                    self.signal.packet_logged.emit()
        # Update cached signal for plots
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
        gain_str = 'High' if gain[0] == 3 else 'Medium' if gain[0] == 2 else 'Low' if gain[0] == 1 else 'Unknown'
        self.signal.new_aux_data.emit([int(wl), gain_str, standardized_frame.led_temp[0],
                                       standardized_frame.water_temp[0], standardized_frame.depth[0],
                                       net_ref_zero_flag[0]])
        self.signal.new_spectrum_data.emit([self.signal_reconstructed])

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


class HyperBBPlaqueCalibration:
    def __init__(self, filename):
        self.processing_version = None
        self.serial_number = None
        self.date = None
        self.temperature_cal_date = None
        self.dark_offset_wl = None
        self.dark_offset_scat1 = None
        self.dark_offset_scat2 = None
        self.dark_offset_scat3 = None
        self.dark_offset_pmt_gain = None
        self.pmt_gamma = None
        self.pmt_gamma_rmse = None
        self.pmt_reference_gain = None
        self.gain12 = None
        self.gain12_std = None
        self.gain23 = None
        self.gain23_std = None
        self.mu_pmt_gain = None
        self.transmit_receive_distance = None
        self.plaque_reflectivity = None
        self.mu_factor_wl = None
        self.mu_factors = None
        self.mu_factor_temp_corr = None
        self.mu_factor_led_temp = None

        self.read(filename)

        # Prepare interpolation tables for dark offsets
        self.f_dark_offset_scat1 = interp2d(self.dark_offset_pmt_gain, self.dark_offset_wl,
                                            self.dark_offset_scat1, kind='linear')
        self.f_dark_offset_scat2 = interp2d(self.dark_offset_pmt_gain, self.dark_offset_wl,
                                            self.dark_offset_scat2, kind='linear')
        self.f_dark_offset_scat3 = interp2d(self.dark_offset_pmt_gain, self.dark_offset_wl,
                                            self.dark_offset_scat3, kind='linear')

    def read(self, filename):
        if str(filename).lower().endswith('.hbb_cal'):
            self._read_binary(filename)
        elif str(filename).lower().endswith('.mat'):
            self._read_mat(filename)
        else:
            raise HyperBBError('Plaque calibration file must be .mat or .hbb_cal')

    def _read_mat(self, plaque_cal_file):
        p = loadmat(plaque_cal_file, simplify_cells=True)['cal']
        if np.any(p['darkCalWavelength'] != p['muWavelengths']):
            raise HyperBBError('Wavelength from calibration files don\'t match.')
        # self.date = p['timestamp']  # Matlab datetime object (not readable)
        self.dark_offset_wl = p['darkCalWavelength']
        self.dark_offset_scat1 = p['darkCalScat1']
        self.dark_offset_scat2 = p['darkCalScat2']
        self.dark_offset_scat3 = p['darkCalScat3']
        self.dark_offset_pmt_gain = p['darkCalPmtGain']
        self.pmt_gamma = p['pmtGamma']
        self.pmt_reference_gain = p['pmtRefGain']
        self.gain12 = p['gain12']
        self.gain23 = p['gain23']
        self.transmit_receive_distance = p['H']
        self.plaque_reflectivity = p['rho']
        self.mu_factor_wl = p['muWavelengths']
        self.mu_factors = p['muFactors']
        self.mu_factor_led_temp = p['muLedTemp']

    @property
    def wl(self):
        return self.mu_factor_wl

    def _read_binary(self, plaque_cal_file):
        with open(plaque_cal_file, 'rb') as f:
            blob = f.read()
        offset = 0
        records = []
        while offset < len(blob):
            start = offset
            if len(blob) - start < 30:
                raise HyperBBError('Truncated HyperBB calibration header.')
            identifier = blob[offset:offset + 24].rstrip(b'\0 ')
            offset += 24
            if identifier != b'Sequoia Hyper-bb Cal':
                raise HyperBBError('Not a Sequoia HyperBB plaque calibration file.')
            length = int.from_bytes(blob[offset:offset + 2], 'little')
            end = start + length
            if length < 76 or end > len(blob):
                raise HyperBBError('Invalid or truncated HyperBB calibration record length.')

            def take(dtype, count=1, scale=1):
                nonlocal offset
                size = np.dtype(dtype).itemsize * count
                if offset + size > end:
                    raise HyperBBError('Truncated HyperBB calibration field.')
                value = np.frombuffer(blob, dtype=dtype, count=count, offset=offset).astype(float) / scale
                offset += size
                return float(value[0]) if count == 1 else value

            def date():
                value = take('u1', 6).astype(int)
                value[0] += 1900
                try:
                    return datetime(*value)
                except ValueError as exc:
                    raise HyperBBError('Invalid date in HyperBB calibration.') from exc
            _record_length = int(take('<u2'))
            c = {
                'processing_version': take('<u2', scale=100),
                'serial_number': int(take('<u2')),
                'date': date(),
                'temperature_cal_date': date(),
                'pmt_reference_gain': take('<u2'),
                'pmt_gamma': take('<f4'),
                'pmt_gamma_rmse': take('<f4'),
                'gain12': take('<u2', scale=1000),
                'gain12_std': take('<f4'),
                'gain23': take('<u2', scale=1000),
                'gain23_std': take('<f4'),
                'mu_pmt_gain': take('<u2'),
                'transmit_receive_distance': take('<u2', scale=100),
                'plaque_reflectivity': take('u1', scale=100)
            }
            n, m, k = (int(take('u1')) for _ in range(3))
            if min(n, m, k) < 2:
                raise HyperBBError('HyperBB calibration requires at least two points per axis.')
            c['mu_factor_wl'] = take('<u2', n, 10)
            c['mu_factors'] = take('<f4', n)
            c['mu_factor_temp_corr'] = take('<f4', n)
            c['mu_factor_led_temp'] = take('<u2', n, 100)
            c['dark_offset_wl'] = take('<u2', m, 10)
            c['dark_offset_pmt_gain'] = take('<u2', k)
            c['dark_offset_scat1'] = take('<f4', m * k).reshape((m, k), order='F')
            c['dark_offset_scat2'] = take('<f4', m * k).reshape((m, k), order='F')
            c['dark_offset_scat3'] = take('<f4', m * k).reshape((m, k), order='F')
            # File Check
            if offset != end:
                raise HyperBBError('Unsupported HyperBB calibration layout: record length mismatch.')
            for name in ('mu_factor_wl', 'dark_offset_wl', 'dark_offset_pmt_gain'):
                if not np.all(np.diff(c[name]) > 0):
                    raise HyperBBError('HyperBB calibration axes must be strictly increasing.')
            values = [c[name] for name in ('mu_factors', 'mu_factor_temp_corr', 'pmt_reference_gain',
                                           'pmt_gamma', 'gain12', 'gain23',
                                           'dark_offset_scat1', 'dark_offset_scat2', 'dark_offset_scat3')]
            if not all(np.all(np.isfinite(value)) for value in values):
                raise HyperBBError('Non-finite values in HyperBB calibration.')
            if any(np.any(np.asarray(c[name]) <= 0) for name in
                   ('mu_factors', 'mu_factor_temp_corr', 'pmt_reference_gain', 'gain12', 'gain23')):
                raise HyperBBError('Non-positive gain or correction factor in HyperBB calibration.')
            records.append(c)
        if not records:
            raise HyperBBError('Empty HyperBB calibration file.')
        # Select last calibration record in file as in Sequoia's matlab code
        for k, v in records[-1].items():
            if not hasattr(self, k):
                raise HyperBBError(f'Unknown HyperBB calibration field: {k}')
            setattr(self, k, v)


class HyperBBTemperatureCalibration:
    def __init__(self, filename):
        self.processing_version = None
        self.serial_number = None
        self.date = None
        self.normalize_temp = None
        self.polynomoial_order = None
        self.wl = None
        self.coeffs = None

        self._min_t, self._max_t = None, None
        self._interp_grid = None

        if filename:
            self.read(filename)

    def read(self, temperature_cal_file):
        if temperature_cal_file.lower().endswith('.hbb_tcal'):
            self._read_binary(temperature_cal_file)
        elif temperature_cal_file.lower().endswith('.mat'):
            self._read_mat(temperature_cal_file)
        else:
            raise HyperBBError('Temperature calibration file must be .mat or .hbb_tcal')

    def _read_mat(self, temperature_cal_file):
        t = loadmat(temperature_cal_file, simplify_cells=True)
        self.wl = np.asarray(t['cal_temp']['wl'], dtype=float)
        self.coeffs = np.asarray(t['cal_temp']['coeff'], dtype=float)
        # self.date = t['cal_temp']['timestamp']
        self.normalize_temp = t['cal_temp']['normalizedTemp']

    def _read_binary(self, filename):
        with open(filename, "rb") as f:
            blob = f.read()
        offset = 0
        end = len(blob)

        def take(dtype, count=1, scale=1):
            nonlocal offset
            size = np.dtype(dtype).itemsize * count
            if offset + size > end:
                raise HyperBBError('Truncated HyperBB temperature calibration field.')
            value = np.frombuffer(blob, dtype=dtype, count=count, offset=offset).astype(float) / scale
            offset += size
            return float(value[0]) if count == 1 else value

        identifier = take('u1', 24).astype(np.uint8).tobytes().decode('ascii').rstrip('\0 ')
        self.processing_version = take('<u2', scale=100)
        self.serial_number = int(take('<u2'))

        date_parts = take('u1', 6).astype(int)
        date_parts[0] += 1900
        try:
            self.date = datetime(*date_parts)
        except ValueError as exc:
            raise HyperBBError('Invalid date in HyperBB temperature calibration.') from exc

        self.normalized_temp = take('<u2', scale=100)
        self.polynomial_order = int(take('u1'))
        num_wavelengths = int(take('u1'))
        self.wl = take('<u2', num_wavelengths, scale=10)
        coefficients = take('<f4', num_wavelengths * (self.polynomial_order + 1))
        self.coeffs = coefficients.reshape((num_wavelengths, self.polynomial_order + 1), order='F')

    def compute_temperature_coefficients(self, wl, t):
        """
        Interpolate temperature correction for given wavelength and temperature
        """
        margin = 0.5  # degC

        t_min, t_max = np.min(t), np.max(t)

        if self._interp_grid is None:
            self._min_t = t_min - margin
            self._max_t = t_max + margin
            self._build_interp_grid()
        elif t_min < self._min_t or t_max > self._max_t:
            self._min_t = t_min - margin
            self._max_t = t_max + margin
            self._build_interp_grid()

        t_correction = self._interp_grid(t, wl)
        return np.diag(t_correction) if t_correction.ndim > 1 else t_correction

    def _build_interp_grid(self):
        # Generate temperature correction grid
        led_t = np.arange(self._min_t, self._max_t + 0.1001, 0.1)
        t_correction = np.empty((len(self.wl), len(led_t)))
        for k in range(len(self.wl)):
            t_correction[k, :] = np.polyval(self.coeffs[k, :], led_t)
        # Temperature correction
        self._interp_grid = interp2d(led_t, self.wl, t_correction, kind='linear')


@dataclass  # slots=True is only available in Python 3.10+
class HyperBBStandardizedFrame:
    scan_idx: Union[int, NDArray[np.int64]]
    wl: Union[int, NDArray[np.int64]]
    scat1: Union[float, NDArray[np.float64]]
    scat2: Union[float, NDArray[np.float64]]
    scat3: Union[float, NDArray[np.float64]]
    net_ref_zero_flag: Union[bool, np.bool_, NDArray[np.bool_]]
    gain: Union[int, NDArray[np.int64]]
    pmt_gain: Union[int, NDArray[np.int64]]
    led_temp: Union[float, NDArray[np.float64]]
    water_temp: Union[float, NDArray[np.float64]]
    depth: Union[float, NDArray[np.float64]]
    temp_corr_factor: Optional[Union[float, NDArray[np.float64]]] = None


class HyperBBFrameFormat(ABC):
    FRAME_VARIABLES: Tuple[str] = ('',)
    FRAME_TYPES: Tuple[Type] = (bool,)
    SATURATION_LEVEL = 4000
    NAME = ''

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.FRAME_VARIABLES:
            return
        cls.N = len(cls.FRAME_VARIABLES)
        # Only derive a default when the subclass didn't explicitly set its own
        if 'FRAME_PRECISIONS' not in cls.__dict__:
            cls.FRAME_PRECISIONS = ['%s'] * cls.N
        # for index, name in enumerate(cls.FRAME_VARIABLES):
        #     setattr(cls, f'idx_{name}', index)
        if 'DTYPE' not in cls.__dict__:
            cls.DTYPE = np.dtype(list(zip(cls.FRAME_VARIABLES, cls.FRAME_TYPES)))

    @classmethod
    def convert_frames_to_structured_array(cls, decoded_frames: Union[list, tuple, NDArray]) -> NDArray:
        """
        Convert a list of frames to a structured array with the same number of fields and order as FRAME_VARIABLES.
        Missing fields are filled with NaN or None.

        :param frames: <list> decoded frame data
        :return: <NDArray> structured array of frame data
        """
        if isinstance(decoded_frames, tuple):
            return np.array([decoded_frames], dtype=cls.DTYPE)
        elif isinstance(decoded_frames, list):
            return np.array([tuple(frame) for frame in decoded_frames], dtype=cls.DTYPE)
        else:  # assume it's already a structured array
            return decoded_frames

    @classmethod
    def standardize(cls, decoded_frames: Union[list, tuple, NDArray]) -> HyperBBStandardizedFrame:
        """
        Convert raw frame(s) to a standardized format with the same number of fields and order as FRAME_VARIABLES.
        Missing fields are filled with NaN or None.

        :param decoded_frames: <list, tuple, or NDArray> decoded frame data
        :return: <list> standardized frame data
        """
        d = cls.convert_frames_to_structured_array(decoded_frames)
        # Remove saturated reading
        d['SigOn1'][d['SigOn1'] > cls.SATURATION_LEVEL] = np.nan
        d['SigOn2'][d['SigOn2'] > cls.SATURATION_LEVEL] = np.nan
        d['SigOn3'][d['SigOn3'] > cls.SATURATION_LEVEL] = np.nan
        d['SigOff1'][d['SigOff1'] > cls.SATURATION_LEVEL] = np.nan
        d['SigOff2'][d['SigOff2'] > cls.SATURATION_LEVEL] = np.nan
        d['SigOff3'][d['SigOff3'] > cls.SATURATION_LEVEL] = np.nan
        # Calculate net signal for ref, low gain (2), high gain (3)
        net_ref = d['RefOn'] - d['RefOff']
        net_sig1 = d['SigOn1'] - d['SigOff1']  # d['NetSig1']
        net_sig2 = d['SigOn2'] - d['SigOff2']
        net_sig3 = d['SigOn3'] - d['SigOff3']
        net_ref_zero_flag = net_ref == 0
        net_ref[net_ref == 0] = np.nan
        scat1 = net_sig1 / net_ref
        scat2 = net_sig2 / net_ref
        scat3 = net_sig3 / net_ref
        # Keep gain setting
        gain = np.ones(len(d)) * 3
        gain[np.isnan(d['SigOn3'])] = 2
        gain[np.isnan(d['SigOn2'])] = 1
        gain[np.isnan(d['SigOn1'])] = 0  # All signals saturated
        # Return standardized frame
        return HyperBBStandardizedFrame(
            scan_idx=d['ScanIdx'],
            wl=d['wl'],
            scat1=scat1,
            scat2=scat2,
            scat3=scat3,
            net_ref_zero_flag=net_ref_zero_flag,
            gain=gain,
            pmt_gain=d['PmtGain'],
            led_temp=d['LedTemp'],
            water_temp=d['WaterTemp'],
            depth=d['Depth'],
            temp_corr_factor=d['TempCorrFactor'] if 'TempCorrFactor' in d.dtype.names else None
        )

    @classproperty
    def name(cls):
        return cls.NAME


class HyperBBLegacyFrameFormat(HyperBBFrameFormat):
    """
    Legacy format: from Sequoia HyperBB User Manual version 1.2
    Field Saturation is named Debug1 Sequoia's Matlab code referring to this frame as V1_69

    Saturation is referred to as Debug1 in Sequoia's Matlab code
    zDistance is referred to as CalPlaqueDist in Sequoia's User Manual v1.2
    """
    NAME = 'legacy'
    FRAME_VARIABLES = (
        'ScanIdx', 'DataIdx', 'Date', 'Time', 'StepPos', 'wl', 'LedPwr', 'PmtGain',
        'NetSig1', 'SigOn1', 'SigOn1Std', 'RefOn', 'RefOnStd', 'SigOff1', 'SigOff1Std',
        'RefOff', 'RefOffStd', 'SigOn2', 'SigOn2Std', 'SigOn3', 'SigOn3Std', 'SigOff2',
        'SigOff2Std', 'SigOff3', 'SigOff3Std', 'LedTemp', 'WaterTemp',
        'Depth', 'Saturation', 'zDistance'
    )
    FRAME_TYPES = (
        int, int, str, str, int, int, int, int, int,
        float, float, float, float, float, float, float,
        float, float, float, float, float, float, float,
        float, float, float, float, float, int, int
    )


class HyperBBAdvancedFrameFormat(HyperBBFrameFormat):
    """
    Advanced format: from Sequoia HyperBB User Manual version 1.3 or firmware version >=1.68
    The advanced output contains extra parameters:
    - The standard deviation can be used as a proxy for particle size.
    - The stepper position can be used to determine wavelength registration in case of instrument issues.

    Referred to as V1_74 in Sequoia's Matlab code, with the following differences:
    - Debug1 is named Saturation in Sequoia's User Manual
    - zDistance is named CalPlaqueDist in Sequoia's User Manual
    """
    NAME = 'advanced'
    FRAME_VARIABLES = (
        'ScanIdx', 'DataIdx', 'Date', 'Time', 'StepPos', 'wl', 'LedPwr', 'PmtGain',
        'NetSig1', 'SigOn1', 'SigOn1Std', 'RefOn', 'RefOnStd', 'SigOff1', 'SigOff1Std',
        'RefOff', 'RefOffStd', 'SigOn2', 'SigOn2Std', 'SigOn3', 'SigOn3Std',
        'SigOff2', 'SigOff2Std', 'SigOff3', 'SigOff3Std', 'LedTemp', 'WaterTemp',
        'Depth', 'SupplyVolts', 'Debug1', 'zDistance'
    )
    FRAME_TYPES = (
        int, int, str, str, int, int, int, int, int,
        float, float, float, float, float, float, float,
        float, float, float, float, float, float, float,
        float, float, float, float, float, float, int, int
    )


class HyperBBAdvancedV175FrameFormat(HyperBBFrameFormat):
    NAME='advanced v1.75'
    FRAME_VARIABLES = (
        'ScanIdx', 'Date', 'Time', 'StepPos', 'wl', 'LedPwr', 'PmtGain',
        'SigOn1', 'SigOn1Std', 'RefOn', 'RefOnStd', 'SigOff1', 'SigOff1Std',
        'RefOff', 'RefOffStd', 'SigOn2', 'SigOn2Std', 'SigOn3', 'SigOn3Std',
        'SigOff2', 'SigOff2Std', 'SigOff3', 'SigOff3Std', 'LedTemp', 'WaterTemp',
        'Depth', 'SupplyVolts', 'TempCorrFactor', 'SaturationPercent', 'zDistance'
    )
    FRAME_TYPES = (
        int, str, str, int, int, int, int, float, float,
        float, float, float, float, float, float, float,
        float, float, float, float, float, float, float,
        float, float, float, float, float, float, int, int
    )


class HyperBBUserFrameFormat(HyperBBFrameFormat):
    """
    Light format: from Sequoia HyperBB User Manual (likely version 1.3)
    """
    NAME = 'user'
    FRAME_VARIABLES = (
        'ScanIdx', 'Date', 'Time', 'wl', 'PmtGain', 'NetRef',
        'NetSig1', 'NetSig2', 'NetSig3', 'LedTemp', 'WaterTemp',
        'Depth', 'SupplyVolts', 'ChSaturated'
    )
    FRAME_TYPES = (
        int, str, str, int, int, float,
        float, float, float, float, float,
        float, float, int
    )

    @classmethod
    def standardize(cls, decoded_frames: Union[list, tuple, NDArray]) -> HyperBBStandardizedFrame:
        d = cls.convert_frames_to_structured_array(decoded_frames)
        d['NetSig1'][d['ChSaturated'] == 1] = np.nan
        d['NetSig2'][(0 < d['ChSaturated']) & (d['ChSaturated'] <= 2)] = np.nan
        d['NetSig3'][(0 < d['ChSaturated']) & (d['ChSaturated'] <= 3)] = np.nan
        net_ref_zero_flag = d['NetRef'] == 0
        d['NetRef'][d['NetRef'] == 0] = np.nan
        scat1 = d['NetSig1'] / d['NetRef']
        scat2 = d['NetSig2'] / d['NetRef']
        scat3 = d['NetSig3'] / d['NetRef']
        # Keep gain setting
        gain = np.ones(len(d), dtype=np.int8) * 3
        gain[d['ChSaturated'] == 3] = 2
        gain[d['ChSaturated'] == 2] = 1
        gain[d['ChSaturated'] == 1] = 0  # All signals saturated
        # Return standardized frame
        return HyperBBStandardizedFrame(
            scan_idx=d['ScanIdx'],
            wl=d['wl'],
            scat1=scat1,
            scat2=scat2,
            scat3=scat3,
            net_ref_zero_flag=net_ref_zero_flag,
            gain=gain,
            pmt_gain=d['PmtGain'],
            led_temp=d['LedTemp'],
            water_temp=d['WaterTemp'],
            depth=d['Depth'],
            temp_corr_factor=d['TempCorrFactor'] if 'TempCorrFactor' in d.dtype.names else None
        )


class HyperBBUserV175FrameFormat(HyperBBUserFrameFormat):
    """
    Light format: from Sequoia HyperBB User Manual

    Suspect this is from V1.75 given that it includes the TempCorrFactor field, which is not present in the V1.74.
    """
    NAME = 'user v1.75'
    FRAME_VARIABLES = (
        'ScanIdx', 'Date', 'Time', 'wl', 'PmtGain', 'NetRef',
        'NetSig1', 'NetSig2', 'NetSig3', 'LedTemp', 'WaterTemp',
        'Depth', 'SupplyVolt', 'TempCorrFactor', 'ChSaturated'
    )
    FRAME_TYPES = (
        int, str, str, int, int, float,
        float, float, float, float, float,
        float, float, float, int
    )


class HyperBBParser:
    def __init__(self, plaque_cal_file, temperature_cal_file='', data_format='auto'):
        # Load calibration files
        self.p_cal = HyperBBPlaqueCalibration(plaque_cal_file)
        self.t_cal = HyperBBTemperatureCalibration(temperature_cal_file)
        self.check_calibration_consistency()

        # Correct mu for temperature
        if self.t_cal.coeffs is None:
            if self.p_cal.mu_factor_temp_corr is not None:
                temp_coeff_mu = self.p_cal.mu_factor_temp_corr
            else:
                raise HyperBBError('You must supply a path to a temperature calibration file '
                                   'or have muFactorTempCorr in the plaque calibration file.')
        else:
            temp_coeff_mu = self.t_cal.compute_temperature_coefficients(self.p_cal.mu_factor_wl, self.p_cal.mu_factor_led_temp)
        self.mu_factors_temp_corrected = self.p_cal.mu_factors * temp_coeff_mu

        # Compute Xp factor
        self.Xp = self.compute_xp(theta=135)

        # Data format
        self.data_format: Optional[Type[HyperBBFrameFormat]] = None
        self.set_data_format(data_format)

        # Remove scans with multiple gains
        self.remove_scans_multiple_gain = False

    @property
    def wavelength(self):
        return self.p_cal.wl

    def check_calibration_consistency(self):
        if self.t_cal.wl is not None and np.any(self.p_cal.wl != self.t_cal.wl):
            raise HyperBBError('Wavelength from plaque and temperature files don\'t match.')

    @staticmethod
    def compute_xp(theta: float = 135) -> float:
        """
        Compute the Xp factor with Sullivan et al. 2013

        :return:
        """
        theta_ref = np.arange(90, 171, 10)
        Xp_ref = np.array([0.684, 0.858, 1.000, 1.097, 1.153, 1.167, 1.156, 1.131, 1.093])
        return float(splev(theta, splrep(theta_ref, Xp_ref)))

    def set_data_format(self, value: str):
        if value == 'auto':
            self.data_format = None
        elif value in ['user', 'light']:  # For backward compatibility with older versions of configuration file
            self.data_format = HyperBBUserFrameFormat
        elif value == 'user v1.75':
            self.data_format = HyperBBUserV175FrameFormat
        elif value == 'advanced':
            self.data_format = HyperBBAdvancedFrameFormat
        elif value == 'advanced v1.75':
            self.data_format = HyperBBAdvancedV175FrameFormat
        elif value == 'legacy':
            self.data_format = HyperBBLegacyFrameFormat
        else:
            raise HyperBBError('Invalid data format. Must be one of: auto, user, user v1.75, advanced, advanced v1.75, or legacy.')

    def detect_data_format(self, decoded_data):
        n = len(decoded_data)
        if n == HyperBBAdvancedFrameFormat.N:  # 31
            self.data_format = HyperBBAdvancedFrameFormat
        elif n == HyperBBUserFrameFormat.N:  # 14
            self.data_format = HyperBBUserFrameFormat
        elif n == HyperBBUserV175FrameFormat.N:  # 15
            self.data_format = HyperBBUserV175FrameFormat
        elif n == HyperBBLegacyFrameFormat.N:  # 30 == HyperBBAdvanceV175FrameFormat.N
            # Same detection method as in Sequoia's Matlab code to differentiate V1.69 and V1.75
            #   which have the same number of fields but different field types
            try:
                int(decoded_data[1])
                self.data_format = HyperBBLegacyFrameFormat
            except (ValueError, TypeError):
                self.data_format = HyperBBAdvancedV175FrameFormat
        else:
            raise HyperBBError('Unsupported data format.')

    def parse(self, raw: bytearray) -> tuple:
        """
        Parse a raw frame from HyperBB and detect the data format if not already set.

        :param raw: bytes, raw frame data from HyperBB
        :return: data: list, parsed data according to the detected format
        """
        tmp = raw.decode().split()
        flag_updated_data_format = False
        if self.data_format is None:
            self.detect_data_format(tmp)
            flag_updated_data_format = True
        return tuple(t(v) for v, t in zip(tmp, self.data_format.FRAME_TYPES)), flag_updated_data_format

    def standardize(self, parsed_data: Union[list, tuple, NDArray]) -> HyperBBStandardizedFrame:
        """
        Standardize the decoded data to a common format for calibration.

        :param parsed_data: <nxN np.ndarray> frames decoded from HyperBB
        :return: standardized_data: <nxM np.ndarray> standardized frames
        """
        if self.data_format is None:
            self.detect_data_format(parsed_data)
        return self.data_format.standardize(parsed_data)

    def calibrate(self, standardized_data: HyperBBStandardizedFrame) -> tuple:
        """
        Calibrate standardized data from HyperBB.

        :param standardized_data: standardized frames typically obtained from the standardize() method
        :return: beta: <nx1 np.ndarray> calibrated volume scattering function
                 bb: <nx1 np.ndarray> calibrated backscattering coefficient
                 wl: <nx1 np.ndarray> wavelength (nm)
                 gain: <nx1 np.ndarray> gain used (1: low, 2: medium, and 3: high)
                 zero_ref_flag: bool, True if any reference signal was zero
        """
        d = standardized_data
        # Remove scans with multiple gains
        if self.remove_scans_multiple_gain and isinstance(d.scan_idx, np.ndarray) and len(d.scan_idx) > 1:
            rows_to_drop = np.zeros(len(d.scan_idx), dtype=bool)
            for scan_idx in np.unique(d.scan_idx):
                sel = d.scan_idx == scan_idx
                if len(np.unique(d.pmt_gain[sel])) > 1:
                    rows_to_drop |= sel
            d = HyperBBStandardizedFrame(
                scan_idx=d.scan_idx[~rows_to_drop],
                wl=d.wl[~rows_to_drop],
                scat1=d.scat1[~rows_to_drop],
                scat2=d.scat2[~rows_to_drop],
                scat3=d.scat3[~rows_to_drop],
                net_ref_zero_flag=d.net_ref_zero_flag[~rows_to_drop],
                gain=d.gain[~rows_to_drop],
                pmt_gain=d.pmt_gain[~rows_to_drop],
                led_temp=d.led_temp[~rows_to_drop],
                water_temp=d.water_temp[~rows_to_drop],
                depth=d.depth[~rows_to_drop],
                temp_corr_factor=d.temp_corr_factor[~rows_to_drop] if d.temp_corr_factor is not None else None
            )
        # Subtract dark offset
        scat1_dark_removed = d.scat1 - self.p_cal.f_dark_offset_scat1(d.pmt_gain, d.wl)
        scat2_dark_removed = d.scat2 - self.p_cal.f_dark_offset_scat2(d.pmt_gain, d.wl)
        scat3_dark_removed = d.scat3 - self.p_cal.f_dark_offset_scat3(d.pmt_gain, d.wl)
        # Apply PMT and front end gain factors
        g_pmt = (d.pmt_gain / self.p_cal.pmt_reference_gain) ** self.p_cal.pmt_gamma
        scat1_gain_corrected = scat1_dark_removed * self.p_cal.gain12 * self.p_cal.gain23 * g_pmt
        scat2_gain_corrected = scat2_dark_removed * self.p_cal.gain23 * g_pmt
        scat3_gain_corrected = scat3_dark_removed * g_pmt
        # Apply temperature Correction
        if self.t_cal.coeffs is None:
            if d.temp_corr_factor is not None:
                temp_coeff = d.temp_corr_factor
            else:
                raise HyperBBError('You must supply a path to a temperature calibration file, '
                                   'or upgrade your HyperBB firmware to output the TempCorrFactor field.')
        else:
            temp_coeff = self.t_cal.compute_temperature_coefficients(d.wl, d.led_temp)
        scat1_t_corrected = scat1_gain_corrected / temp_coeff
        scat2_t_corrected = scat2_gain_corrected / temp_coeff
        scat3_t_corrected = scat3_gain_corrected / temp_coeff
        # Select highest non-saturated gain channel
        scatx_corrected = scat3_t_corrected  # default is high gain
        scatx_corrected[np.isnan(scatx_corrected)] = scat2_t_corrected[
            np.isnan(scatx_corrected)]  # otherwise low gain
        scatx_corrected[np.isnan(scatx_corrected)] = scat1_t_corrected[
            np.isnan(scatx_corrected)]  # otherwise raw pmt
        # Calculate beta
        beta_u = np.full(len(d.wl), np.nan)
        for kwl in np.unique(d.wl):
            mask = d.wl == kwl
            if kwl in self.p_cal.wl:
                mu = self.mu_factors_temp_corrected[self.p_cal.wl == kwl]
            else:
                mu = pchip_interpolate(self.p_cal.wl, self.mu_factors_temp_corrected, kwl)
            beta_u[mask] = scatx_corrected[mask] * mu
        # Calculate backscattering
        bb = 2 * np.pi * self.Xp * beta_u
        return beta_u, bb, d.wl, d.gain, d.net_ref_zero_flag


class HyperBBError(Exception):
    pass
