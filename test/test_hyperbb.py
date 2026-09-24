"""Run with: python -m unittest discover -s test -p 'test_hyperbb.py'.

Fixtures are generated synthetic data, not an instrument's calibration.
The real HyperBB and base Instrument classes are used without opening a port.
"""
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import savemat

from inlinino.instruments.hyperbb import HyperBB, HyperBBParser
from inlinino.instruments.hyperbb_binary import read_binary_calibration


def binary_record(serial=8040, day=29, version=250, mu_scale=1):
    record = bytearray(b'Sequoia Hyper-bb Cal'.ljust(24, b'\0'))
    record.extend(struct.pack('<HHH', 0, version, serial))
    record.extend(bytes([126, 4, day, 14, 3, 36, 126, 4, 28, 20, 41, 5]))
    record.extend(struct.pack('<HffHfHfHHBBBB',
                              2000, -2, 0, 2000, 0, 3000, 0,
                              1150, 3140, 110, 3, 2, 2))
    record.extend(struct.pack('<3H', 4300, 4400, 4500))
    record.extend(struct.pack('<3f', 2 * mu_scale, 4 * mu_scale, 6 * mu_scale))
    record.extend(struct.pack('<3f', .5, 1, 2))
    record.extend(struct.pack('<3H', 2500, 2500, 2500))
    record.extend(struct.pack('<2H', 4300, 4500))
    record.extend(struct.pack('<2H', 1000, 2000))
    for channel in range(1, 4):
        # MATLAB column order for [[.125, .25], [.375, .5]] * channel.
        record.extend(struct.pack('<4f', *[v * channel for v in [.125, .375, .25, .5]]))
    struct.pack_into('<H', record, 24, len(record))
    return bytes(record)


def packet(saturation=0, factor=2, wl=440, gain=1500, reference=2):
    return ('1 2026/04/29 15:00:00 %s %s %s 2 6 12 25 24 1 14 %s %s' %
            (wl, gain, reference, factor, saturation)).encode()


class Signal:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)

    def __getitem__(self, key):
        return self


class Signals:
    def __init__(self):
        for name in ('status_update', 'packet_received', 'packet_logged', 'packet_corrupted',
                     'new_ts_data', 'new_aux_data', 'new_spectrum_data', 'alarm_custom', 'alarm'):
            setattr(self, name, Signal())


class HyperBBTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.cal_path = self.root / 'synthetic.hbb_cal'
        self.cal_path.write_bytes(binary_record())

    def parser(self):
        return HyperBBParser(str(self.cal_path), '', 'light')

    def config(self, **kwargs):
        cfg = dict(module='hyperbb', manufacturer='Sequoia', model='HyperBB', serial_number='8040',
                   log_path=str(self.root / 'logs'), log_raw=True, log_products=True,
                   plaque_file=str(self.cal_path), data_format='light')
        cfg.update(kwargs)
        return cfg

    def instrument(self, **kwargs):
        result = HyperBB('test', self.config(**kwargs), Signals())
        self.addCleanup(result.log_stop)
        return result

    def test_record_fields_and_matlab_array_order(self):
        c = read_binary_calibration(self.cal_path)
        self.assertEqual(c['serial_number'], 8040)
        self.assertEqual(c['version'], 2.5)
        self.assertEqual(c['date'].isoformat(), '2026-04-29T14:03:36')
        self.assertEqual(c['temperature_date'].isoformat(), '2026-04-28T20:41:05')
        self.assertEqual(c['gain12'], 2)
        self.assertEqual(c['gain23'], 3)
        self.assertEqual(c['transmit_receive_distance'], 31.4)
        self.assertEqual(c['plaque_reflectivity'], 1.1)
        np.testing.assert_array_equal(c['wavelength'], [430, 440, 450])
        np.testing.assert_array_equal(c['dark'][0], [[.125, .25], [.375, .5]])

    def test_last_record_is_selected_in_file_order(self):
        self.cal_path.write_bytes(binary_record(day=29) + binary_record(day=28, mu_scale=2))
        c = read_binary_calibration(self.cal_path)
        self.assertEqual(c['record_count'], 2)
        self.assertEqual(c['date'].day, 28)
        np.testing.assert_equal(c['mu'], [4, 8, 12])

    def test_mixed_instrument_history_is_rejected(self):
        self.cal_path.write_bytes(binary_record() + binary_record(serial=8024))
        with self.assertRaisesRegex(ValueError, 'different instrument serial'):
            read_binary_calibration(self.cal_path)

    def test_malformed_records_are_rejected(self):
        record = binary_record()
        cases = [b'', record[:24], record[:-1], record + b'bad', b'X' + record[1:],
                 binary_record(version=999)]
        for value in cases:
            with self.subTest(length=len(value)):
                self.cal_path.write_bytes(value)
                with self.assertRaises(ValueError):
                    read_binary_calibration(self.cal_path)

    def test_nonmonotonic_grid_is_rejected(self):
        record = bytearray(binary_record())
        # The first wavelength array begins at byte 76.
        struct.pack_into('<3H', record, 76, 4300, 4300, 4500)
        self.cal_path.write_bytes(record)
        with self.assertRaisesRegex(ValueError, 'strictly increasing'):
            read_binary_calibration(self.cal_path)

    def test_schema_contains_temperature_factor(self):
        p = self.parser()
        row = p.parse(packet())
        self.assertEqual(len(row), 15)
        self.assertEqual(p.FRAME_VARIABLES[13], 'TempCorrFactor')
        self.assertEqual(row[p.idx_TempCorrFactor], 2)
        self.assertEqual(p.parse(b' '.join(packet().split()[:13] + packet().split()[14:])), [])

    def test_bilinear_dark_and_gain_corrections(self):
        p = self.parser()
        rows = np.array([p.parse(packet())])
        original = rows.copy()
        beta, bb, wl, gain, zero = p.calibrate(rows)
        # At wl=440, gain=1500: channel-3 dark=.9375; PMT factor=16/9.
        # ((12/2 - .9375) * (16/9) / 2) * (mu=4 * plaque factor=1) = 18.
        np.testing.assert_allclose(beta, [18])
        np.testing.assert_allclose(bb, [2 * np.pi * p.Xp * 18])
        np.testing.assert_array_equal(gain, [[3]])
        np.testing.assert_array_equal(wl, [440])
        np.testing.assert_equal(rows, original)
        self.assertFalse(zero)

    def test_plaque_factor_multiplies_and_live_factor_divides(self):
        p = self.parser()
        rows = np.array([p.parse(packet(wl=430, gain=1000)),
                         p.parse(packet(wl=430, gain=1000, factor=4))])
        beta, *_ = p.calibrate(rows)
        # Channel-3 dark=.375; PMT factor=4; mu*plaque factor=2*.5=1.
        np.testing.assert_allclose(beta, [11.25, 5.625])

    def test_saturation_falls_back_between_channels(self):
        p = self.parser()
        data = np.array([p.parse(packet(saturation=s)) for s in (0, 3, 2, 1)])
        beta, _, _, gains, _ = p.calibrate(data)
        # Channel-2 and channel-1 darks are .625 and .3125 at the midpoint.
        np.testing.assert_allclose(beta[:3], [18, (3 - .625) * 3 * (16/9) / 2 * 4,
                                              (1 - .3125) * 6 * (16/9) / 2 * 4])
        self.assertTrue(np.isnan(beta[3]))
        np.testing.assert_array_equal(gains[:, 0], [3, 2, 1, 0])

    def test_invalid_packets_rejected(self):
        p = self.parser()
        for factor in ('nan', 'inf', 0, -1, 'bad'):
            self.assertEqual(p.parse(packet(factor=factor)), [])
        self.assertEqual(p.parse(packet(saturation=4)), [])
        self.assertEqual(p.parse(packet(gain=0)), [])
        self.assertEqual(p.parse(b''), [])

    def test_zero_reference_and_outside_calibration_domain(self):
        p = self.parser()
        values = [packet(reference=0), packet(wl=429), packet(wl=451),
                  packet(gain=999), packet(gain=2001)]
        for value in values:
            with self.subTest(packet=value):
                beta, _, _, gain, zero = p.calibrate(np.array([p.parse(value)]))
                self.assertTrue(np.isnan(beta[0]))
                self.assertEqual(gain[0, 0], 0)
        self.assertTrue(p.calibrate(np.array([p.parse(packet(reference=0))]))[-1])

    def test_binary_requires_light_mode(self):
        for mode in ('legacy', 'advanced'):
            with self.assertRaisesRegex(ValueError, 'Light format'):
                HyperBBParser(str(self.cal_path), '', mode)

    def test_full_instrument_startup_and_reload(self):
        # Regression for accessing parser-local binary_file in HyperBB.__init__.
        obj = self.instrument()
        self.assertEqual(obj.name, 'HyperBB 8040')
        self.assertEqual(obj.variable_names[13], 'TempCorrFactor')
        self.assertEqual(len(obj.variable_names), 17)
        obj.setup(self.config())
        self.assertIsNotNone(obj._parser._binary_calibration)

    def test_serial_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'serial number'):
            self.instrument(serial_number='8024')

    def test_raw_logging_and_plot_updates_from_fragmented_crlf(self):
        obj = self.instrument()
        obj.log_start()
        timestamp = 1777474800.125
        messages = [packet(), b'', packet(saturation=3)]
        for message in messages:
            wire = message + b'\r\n'
            middle = len(wire) // 2
            obj.data_received(wire[:middle], timestamp)
            obj.data_received(wire[middle:], timestamp)
        obj.log_stop()
        self.assertEqual(len(obj.signal.new_spectrum_data.calls), 2)
        self.assertEqual(obj.signal.packet_corrupted.calls, [])
        raw = next((self.root / 'logs').glob('*.raw')).read_text().splitlines()[2:]
        self.assertEqual([line.split(',', 1)[1] for line in raw], [m.decode() for m in messages])
        products = next((self.root / 'logs').glob('*.csv')).read_text().splitlines()
        self.assertIn('TempCorrFactor', products[0])
        self.assertEqual(len(products[2:]), 2)
        self.assertTrue(all(len(line.split(',')) == 18 for line in products[2:]))

    def test_legacy_mat_calibration_and_all_instrument_modes(self):
        plaque, temp = self.root / 'plaque.mat', self.root / 'temp.mat'
        wl = np.array([430., 440., 450.])
        savemat(plaque, {'cal': dict(darkCalWavelength=wl, darkCalPmtGain=[1000., 2000.],
                                    darkCalScat1=np.zeros((3, 2)), darkCalScat2=np.zeros((3, 2)),
                                    darkCalScat3=np.zeros((3, 2)), pmtRefGain=2000., pmtGamma=-2.,
                                    gain12=2., gain23=3., muWavelengths=wl, muFactors=[2., 4., 6.],
                                    muLedTemp=[25., 25., 25.])})
        savemat(temp, {'cal_temp': dict(wl=wl, coeff=np.tile([0., 0., 1.], (3, 1)))})
        for mode in ('light', 'advanced', 'legacy'):
            obj = self.instrument(plaque_file=str(plaque), temperature_file=str(temp), data_format=mode)
            self.assertIsNone(obj._parser._binary_calibration)
            self.assertNotIn('TempCorrFactor', obj._parser.FRAME_VARIABLES)
            p = obj._parser
            values = dict(ScanIdx='1', DataIdx='1', Date='2026/04/29', Time='15:00:00',
                          wl='440', PmtGain='1500', LedTemp='25', NetRef='2', RefOn='3', RefOff='1',
                          NetSig1='2', NetSig2='6', NetSig3='12', SigOn1='3', SigOff1='1',
                          SigOn2='7', SigOff2='1', SigOn3='13', SigOff3='1', ChSaturated='0')
            message = ' '.join(values.get(name, '0') for name in p.FRAME_VARIABLES).encode()
            beta, *_ = p.calibrate(np.array([p.parse(message)]))
            np.testing.assert_allclose(beta, [(12/2) * (16/9) * 4])


if __name__ == '__main__':
    unittest.main()
