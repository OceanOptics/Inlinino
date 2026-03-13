"""
Tests for HyperBB instrument parser.

Tests the following:
- Old two-file calibration format (plaque + temperature)
- New combined single-file calibration format
- All data output formats (legacy, advanced, light, standard)
- Calibration math (calibrate function)
- Frame parsing
"""
import os
import sys

import numpy as np
import pytest

# Allow running from repo root or test/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inlinino.instruments.hyperbb import (
    HyperBBParser,
    LEGACY_DATA_FORMAT,
    ADVANCED_DATA_FORMAT,
    LIGHT_DATA_FORMAT,
    STANDARD_DATA_FORMAT,
)

CFG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'inlinino', 'cfg')
PLAQUE_CAL = os.path.join(CFG_DIR, 'HBB8005_CalPlaque_20210315.mat')
TEMP_CAL = os.path.join(CFG_DIR, 'HBB8005_CalTemp_20210315.mat')
COMBINED_CAL = os.path.join(CFG_DIR, 'HBB8005_Cal_new_format_example.mat')


def _skip_if_no_cal_files():
    """Skip test if calibration files are not available."""
    return pytest.mark.skipif(
        not os.path.exists(PLAQUE_CAL) or not os.path.exists(TEMP_CAL),
        reason='Calibration files not available'
    )


class TestHyperBBParserCreation:
    """Test HyperBBParser can be created with various configurations."""

    @_skip_if_no_cal_files()
    def test_old_format_advanced(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced')
        assert parser.data_format == ADVANCED_DATA_FORMAT
        assert len(parser.FRAME_VARIABLES) == 31
        assert len(parser.wavelength) > 0

    @_skip_if_no_cal_files()
    def test_old_format_legacy(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'legacy')
        assert parser.data_format == LEGACY_DATA_FORMAT
        assert len(parser.FRAME_VARIABLES) == 30

    @_skip_if_no_cal_files()
    def test_old_format_light(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'light')
        assert parser.data_format == LIGHT_DATA_FORMAT
        assert len(parser.FRAME_VARIABLES) == 14

    @_skip_if_no_cal_files()
    def test_old_format_standard(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'standard')
        assert parser.data_format == STANDARD_DATA_FORMAT
        assert len(parser.FRAME_VARIABLES) == 18

    @_skip_if_no_cal_files()
    def test_new_combined_format(self):
        """New combined calibration file (single file with both plaque and temperature data)."""
        if not os.path.exists(COMBINED_CAL):
            pytest.skip('Combined calibration file not available')
        parser = HyperBBParser(COMBINED_CAL, None, 'advanced')
        assert parser.data_format == ADVANCED_DATA_FORMAT
        assert len(parser.wavelength) > 0

    @_skip_if_no_cal_files()
    def test_new_combined_format_matches_old(self):
        """Combined format should produce same calibration as old two-file format."""
        if not os.path.exists(COMBINED_CAL):
            pytest.skip('Combined calibration file not available')
        parser_old = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced')
        parser_new = HyperBBParser(COMBINED_CAL, None, 'advanced')
        np.testing.assert_array_almost_equal(parser_old.mu, parser_new.mu)
        np.testing.assert_array_equal(parser_old.wavelength, parser_new.wavelength)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match='Data format not recognized'):
            HyperBBParser('dummy.mat', 'dummy.mat', 'invalid_format')

    @_skip_if_no_cal_files()
    def test_old_format_without_temp_file_raises(self):
        """Old two-file format requires temperature file."""
        with pytest.raises(ValueError, match='Missing temperature calibration file'):
            HyperBBParser(PLAQUE_CAL, None, 'advanced')


class TestHyperBBParserParse:
    """Test frame parsing for all data formats."""

    @_skip_if_no_cal_files()
    def test_parse_advanced_frame(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced')
        # 31 space-separated fields
        packet = (b'1 1 2021-01-01 12:00:00 100 450 255 2000 100 '
                  b'500 10 1000 20 400 10 900 20 '
                  b'600 15 700 20 500 15 600 20 '
                  b'36.6 20.0 10.0 12.0 0 1')
        data = parser.parse(packet)
        assert len(data) == len(parser.FRAME_VARIABLES)
        assert data[parser.idx_wl] == float('nan') or data[parser.idx_wl] == 450

    @_skip_if_no_cal_files()
    def test_parse_light_frame(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'light')
        # 14 space-separated fields
        packet = b'1 2021-01-01 12:00:00 450 2000 1000.0 100.0 90.0 80.0 36.6 20.0 10.0 12.0 0'
        data = parser.parse(packet)
        assert len(data) == len(parser.FRAME_VARIABLES)

    @_skip_if_no_cal_files()
    def test_parse_standard_frame(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'standard')
        # 18 space-separated fields
        packet = b'1 1 2021-01-01 12:00:00 100 450 255 2000 1000.0 100.0 90.0 80.0 36.6 20.0 10.0 12.0 0 1'
        data = parser.parse(packet)
        assert len(data) == len(parser.FRAME_VARIABLES)

    @_skip_if_no_cal_files()
    def test_parse_wrong_field_count_returns_empty(self):
        """Short packet should return empty list."""
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced')
        packet = b'1 2 3'
        data = parser.parse(packet)
        assert data == []

    @_skip_if_no_cal_files()
    def test_parse_empty_packet_returns_empty(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced')
        data = parser.parse(b'')
        assert data == []


class TestHyperBBCalibrate:
    """Test calibration calculations."""

    @_skip_if_no_cal_files()
    def test_calibrate_advanced_single_frame(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced')
        n = len(parser.FRAME_VARIABLES)
        raw = np.zeros((1, n))
        raw[0, parser.idx_wl] = 450.0
        raw[0, parser.idx_PmtGain] = 2000.0
        raw[0, parser.idx_NetSig1] = 100.0
        raw[0, parser.idx_SigOn1] = 500.0
        raw[0, parser.idx_SigOn2] = 600.0
        raw[0, parser.idx_SigOn3] = 700.0
        raw[0, parser.idx_SigOff1] = 400.0
        raw[0, parser.idx_SigOff2] = 500.0
        raw[0, parser.idx_SigOff3] = 600.0
        raw[0, parser.idx_RefOn] = 1000.0
        raw[0, parser.idx_RefOff] = 900.0
        raw[0, parser.idx_LedTemp] = 36.6
        beta_u, bb, wl, gain, net_ref_zero_flag = parser.calibrate(raw.copy())
        assert beta_u.shape == (1,)
        assert bb.shape == (1,)
        assert not np.isnan(beta_u[0])
        assert not np.isnan(bb[0])
        assert bb[0] > 0

    @_skip_if_no_cal_files()
    def test_calibrate_standard_single_frame(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'standard')
        n = len(parser.FRAME_VARIABLES)
        raw = np.zeros((1, n))
        raw[0, parser.idx_wl] = 450.0
        raw[0, parser.idx_PmtGain] = 2000.0
        raw[0, parser.idx_NetRef] = 1000.0
        raw[0, parser.idx_NetSig1] = 100.0
        raw[0, parser.idx_NetSig2] = 90.0
        raw[0, parser.idx_NetSig3] = 80.0
        raw[0, parser.idx_LedTemp] = 36.6
        raw[0, parser.idx_Saturation] = 0
        beta_u, bb, wl, gain, net_ref_zero_flag = parser.calibrate(raw.copy())
        assert beta_u.shape == (1,)
        assert bb.shape == (1,)
        assert not np.isnan(bb[0])
        assert bb[0] > 0

    @_skip_if_no_cal_files()
    def test_calibrate_light_single_frame(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'light')
        n = len(parser.FRAME_VARIABLES)
        raw = np.zeros((1, n))
        raw[0, parser.idx_wl] = 450.0
        raw[0, parser.idx_PmtGain] = 2000.0
        raw[0, parser.idx_NetRef] = 1000.0
        raw[0, parser.idx_NetSig1] = 100.0
        raw[0, parser.idx_NetSig2] = 90.0
        raw[0, parser.idx_NetSig3] = 80.0
        raw[0, parser.idx_LedTemp] = 36.6
        raw[0, parser.idx_ChSaturated] = 0
        beta_u, bb, wl, gain, net_ref_zero_flag = parser.calibrate(raw.copy())
        assert not np.isnan(bb[0])
        assert bb[0] > 0

    @_skip_if_no_cal_files()
    def test_calibrate_new_format_matches_old(self):
        """Combined calibration format should produce same calibration results as old format."""
        if not os.path.exists(COMBINED_CAL):
            pytest.skip('Combined calibration file not available')
        parser_old = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced')
        parser_new = HyperBBParser(COMBINED_CAL, None, 'advanced')
        n = len(parser_old.FRAME_VARIABLES)
        raw = np.zeros((1, n))
        raw[0, parser_old.idx_wl] = 450.0
        raw[0, parser_old.idx_PmtGain] = 2000.0
        raw[0, parser_old.idx_NetSig1] = 100.0
        raw[0, parser_old.idx_SigOn1] = 500.0
        raw[0, parser_old.idx_SigOn2] = 600.0
        raw[0, parser_old.idx_SigOn3] = 700.0
        raw[0, parser_old.idx_SigOff1] = 400.0
        raw[0, parser_old.idx_SigOff2] = 500.0
        raw[0, parser_old.idx_SigOff3] = 600.0
        raw[0, parser_old.idx_RefOn] = 1000.0
        raw[0, parser_old.idx_RefOff] = 900.0
        raw[0, parser_old.idx_LedTemp] = 36.6
        beta_u_old, bb_old, _, _, _ = parser_old.calibrate(raw.copy())
        beta_u_new, bb_new, _, _, _ = parser_new.calibrate(raw.copy())
        np.testing.assert_array_almost_equal(bb_old, bb_new)


if __name__ == '__main__':
    # Run tests without pytest for quick validation
    import traceback
    tests = [
        TestHyperBBParserCreation(),
        TestHyperBBParserParse(),
        TestHyperBBCalibrate(),
    ]
    passed = failed = skipped = 0
    for test_obj in tests:
        for method_name in [m for m in dir(test_obj) if m.startswith('test_')]:
            method = getattr(test_obj, method_name)
            try:
                method()
                print(f'PASS: {type(test_obj).__name__}.{method_name}')
                passed += 1
            except Exception as e:
                if 'Skipped' in type(e).__name__ or 'skip' in type(e).__name__.lower():
                    print(f'SKIP: {type(test_obj).__name__}.{method_name}: {e}')
                    skipped += 1
                else:
                    print(f'FAIL: {type(test_obj).__name__}.{method_name}: {e}')
                    traceback.print_exc()
                    failed += 1
    print(f'\nTotal: {passed} passed, {failed} failed, {skipped} skipped')
