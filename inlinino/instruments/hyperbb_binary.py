"""HyperBB v2.5 binary calibration and 15-field User telemetry support.

Equations follow Sequoia Hbb_Process.m, revision 2025-12-08.
Raw logging remains the responsibility of Instrument.handle_packet.
"""
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.interpolate import RegularGridInterpolator, PchipInterpolator

USER_FIELDS = ['ScanIdx', 'Date', 'Time', 'wl', 'PmtGain', 'NetRef',
               'NetSig1', 'NetSig2', 'NetSig3', 'LedTemp', 'WaterTemp',
               'Depth', 'SupplyVolt', 'TempCorrFactor', 'ChSaturated']
USER_TYPES = [int, str, str, int, int, float, float, float, float,
              float, float, float, float, float, int]


def read_binary_calibration(filename):
    """Read complete records; select the last record as Sequoia's script does.

    Layout is Hbb_ReadBinaryCalFile.m (little-endian, MATLAB column order).
    Version 2.50 is the supported processing version for the selected record.
    """
    blob = Path(filename).read_bytes()
    offset = 0
    records = []
    while offset < len(blob):
        start = offset
        if len(blob) - start < 30:
            raise ValueError('Truncated HyperBB calibration header.')
        identifier = blob[offset:offset + 24].rstrip(b'\0 ')
        offset += 24
        if identifier != b'Sequoia Hyper-bb Cal':
            raise ValueError('Not a Sequoia HyperBB plaque calibration file.')
        length = int.from_bytes(blob[offset:offset + 2], 'little')
        end = start + length
        if length < 76 or end > len(blob):
            raise ValueError('Invalid or truncated HyperBB calibration record length.')

        def take(dtype, count=1, scale=1):
            nonlocal offset
            size = np.dtype(dtype).itemsize * count
            if offset + size > end:
                raise ValueError('Truncated HyperBB calibration field.')
            value = np.frombuffer(blob, dtype=dtype, count=count, offset=offset).astype(float) / scale
            offset += size
            return float(value[0]) if count == 1 else value

        def date():
            value = take('u1', 6).astype(int)
            value[0] += 1900
            try:
                return datetime(*value)
            except ValueError as exc:
                raise ValueError('Invalid date in HyperBB calibration.') from exc

        c = {'record_length': int(take('<u2')), 'version': take('<u2', scale=100),
             'serial_number': int(take('<u2')), 'date': date(), 'temperature_date': date()}
        c['pmt_ref_gain'] = take('<u2')
        c['pmt_gamma'] = take('<f4')
        c['pmt_gamma_rmse'] = take('<f4')
        c['gain12'] = take('<u2', scale=1000)
        c['gain12_std'] = take('<f4')
        c['gain23'] = take('<u2', scale=1000)
        c['gain23_std'] = take('<f4')
        c['mu_pmt_gain'] = take('<u2')
        c['transmit_receive_distance'] = take('<u2', scale=100)
        c['plaque_reflectivity'] = take('u1', scale=100)
        n, m, k = (int(take('u1')) for _ in range(3))
        if min(n, m, k) < 2:
            raise ValueError('HyperBB calibration requires at least two points per axis.')
        c['wavelength'] = take('<u2', n, 10)
        c['mu'] = take('<f4', n)
        c['mu_temperature_factor'] = take('<f4', n)
        c['mu_led_temperature'] = take('<u2', n, 100)
        c['dark_wavelength'] = take('<u2', m, 10)
        c['dark_pmt_gain'] = take('<u2', k)
        c['dark'] = [take('<f4', m * k).reshape((m, k), order='F') for _ in range(3)]
        if offset != end:
            raise ValueError('Unsupported HyperBB calibration layout: record length mismatch.')
        for name in ('wavelength', 'dark_wavelength', 'dark_pmt_gain'):
            if not np.all(np.diff(c[name]) > 0):
                raise ValueError('HyperBB calibration axes must be strictly increasing.')
        values = [c[name] for name in ('mu', 'mu_temperature_factor', 'pmt_ref_gain',
                                      'pmt_gamma', 'gain12', 'gain23')] + c['dark']
        if not all(np.all(np.isfinite(value)) for value in values):
            raise ValueError('Non-finite values in HyperBB calibration.')
        if any(np.any(np.asarray(c[name]) <= 0) for name in
               ('mu', 'mu_temperature_factor', 'pmt_ref_gain', 'gain12', 'gain23')):
            raise ValueError('Non-positive gain or correction factor in HyperBB calibration.')
        records.append(c)
    if not records:
        raise ValueError('Empty HyperBB calibration file.')
    if len({r['serial_number'] for r in records}) != 1:
        raise ValueError('HyperBB calibration records contain different instrument serial numbers.')
    selected = records[-1]
    if selected['version'] != 2.5:
        raise ValueError('Binary calibration supports processing version 2.50; '
                         'selected record is %.2f.' % selected['version'])
    selected['record_count'] = len(records)
    return selected


class BinaryCalibration:
    """Calibrate 15-field User/Light rows using onboard temperature factors."""

    def __init__(self, filename):
        self.cal = read_binary_calibration(filename)
        c = self.cal
        self.wavelength = c['wavelength']
        self.dark = [RegularGridInterpolator((c['dark_wavelength'], c['dark_pmt_gain']),
                                            values, method='linear', bounds_error=False,
                                            fill_value=np.nan) for values in c['dark']]
        self.mu = PchipInterpolator(c['wavelength'], c['mu'] * c['mu_temperature_factor'],
                                    extrapolate=False)

    def calibrate(self, raw, xp):
        data = np.asarray(raw, dtype=float)
        if data.ndim != 2 or data.shape[1] != len(USER_FIELDS):
            raise ValueError('Binary HyperBB calibration requires 15-field User/Light data.')
        wl, pmt, ref, factor, saturation = (data[:, i] for i in (3, 4, 5, 13, 14))
        zero_ref = bool(np.any(ref == 0))
        valid = (np.isfinite(data[:, 3:]).all(axis=1) & (ref != 0) &
                 (factor > 0) & (pmt > 0) & np.isin(saturation, [0, 1, 2, 3]))
        c = self.cal
        result = np.full((len(data), 3), np.nan)
        points = np.column_stack((wl, pmt))
        with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
            pmt_correction = (pmt / c['pmt_ref_gain']) ** c['pmt_gamma']
            for channel, front_gain in enumerate((c['gain12'] * c['gain23'], c['gain23'], 1)):
                result[:, channel] = ((data[:, 6 + channel] / ref - self.dark[channel](points)) *
                                      front_gain * pmt_correction / factor)
                saturated = (saturation > 0) & (saturation <= channel + 1)
                result[~valid | saturated, channel] = np.nan
        selected = np.full(len(data), np.nan)
        gain = np.zeros((len(data), 1))
        for channel in range(3):
            usable = np.isfinite(result[:, channel])
            selected[usable] = result[usable, channel]
            gain[usable, 0] = channel + 1
        beta = selected * self.mu(wl)
        gain[~np.isfinite(beta), 0] = 0
        bb = 2 * np.pi * xp * beta
        return beta, bb, wl.copy(), gain, zero_ref
