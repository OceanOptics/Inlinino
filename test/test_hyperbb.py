"""
Tests for HyperBB instrument parser.

Tests the following:
- Legacy calibration format (two separate plaque + temperature .mat files)
- Current calibration format (binary .hbb_cal and .hbb_tcal files produced by
  Hbb_ConvertCalibrations.m, Sequoia Scientific 2024)
- All data output formats (legacy, advanced, light)
- Calibration math (calibrate function)
- Frame parsing
"""
import io
import os
import struct
import sys
import tempfile

import numpy as np
import pytest

# Allow running from repo root or test/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inlinino.instruments.hyperbb import (
    HyperBBParser,
    LEGACY_DATA_FORMAT,
    ADVANCED_DATA_FORMAT,
    LIGHT_DATA_FORMAT,
)

CFG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'inlinino', 'cfg')
PLAQUE_CAL = os.path.join(CFG_DIR, 'HBB8005_CalPlaque_20210315.mat')
TEMP_CAL   = os.path.join(CFG_DIR, 'HBB8005_CalTemp_20210315.mat')


def _skip_if_no_cal_files():
    """Skip test if calibration .mat files are not available."""
    return pytest.mark.skipif(
        not os.path.exists(PLAQUE_CAL) or not os.path.exists(TEMP_CAL),
        reason='Calibration files not available'
    )


# ---------------------------------------------------------------------------
# Helpers: write binary calibration files from existing .mat data
# ---------------------------------------------------------------------------

def _write_hbb_cal(p_cal, path):
    """Serialise a plaque calibration dict to an .hbb_cal binary file.

    Follows the format expected by Hbb_ReadBinaryCalFile.m (Sequoia, 2024):
    MATLAB writes 2-D arrays column-major, so we use Fortran order when
    flattening NumPy arrays before writing.
    """
    dark_wl    = np.asarray(p_cal['darkCalWavelength'], dtype=float)
    dark_gain  = np.asarray(p_cal['darkCalPmtGain'],    dtype='<u2')
    mu_wl      = np.asarray(p_cal['muWavelengths'],     dtype=float)
    mu_factors = np.asarray(p_cal['muFactors'],         dtype='<f4')
    mu_led     = np.asarray(p_cal['muLedTemp'],         dtype=float)
    dark_s1    = np.asarray(p_cal['darkCalScat1'],      dtype='<f4')
    dark_s2    = np.asarray(p_cal['darkCalScat2'],      dtype='<f4')
    dark_s3    = np.asarray(p_cal['darkCalScat3'],      dtype='<f4')
    num_mu_wl    = len(mu_wl)
    num_dark_wl  = len(dark_wl)
    num_dark_gain = len(dark_gain)

    buf = io.BytesIO()
    buf.write(b'Sequoia Hyper-bb Cal' + bytes(4))        # 24-byte ID
    buf.write(struct.pack('<H', 0))                       # calLengthBytes placeholder
    buf.write(struct.pack('<H', 100))                     # processingVersion * 100
    buf.write(struct.pack('<H', 8005))                    # serialNumber
    buf.write(bytes(6))                                    # cal date
    buf.write(bytes(6))                                    # tempCalDate
    buf.write(struct.pack('<H', int(p_cal['pmtRefGain'])))
    buf.write(np.float32(p_cal['pmtGamma']).tobytes())
    buf.write(np.float32(0.0).tobytes())                   # PMTGammaRMSE
    buf.write(struct.pack('<H', round(p_cal['gain12'] * 1000)))
    buf.write(np.float32(0.0).tobytes())                   # gain1_2_std
    buf.write(struct.pack('<H', round(p_cal['gain23'] * 1000)))
    buf.write(np.float32(0.0).tobytes())                   # gain2_3_std
    buf.write(struct.pack('<H', 0))                       # muFactorPMTGain
    buf.write(struct.pack('<H', 0))                       # transmitReceiveDistance
    buf.write(struct.pack('B', 0))                        # plaqueReflectivity
    buf.write(struct.pack('B', num_mu_wl))
    buf.write(struct.pack('B', num_dark_wl))
    buf.write(struct.pack('B', num_dark_gain))
    buf.write((mu_wl * 10).round().astype('<u2').tobytes())
    buf.write(mu_factors.tobytes())
    buf.write(np.zeros(num_mu_wl, dtype='<f4').tobytes())  # muFactorTempCorr (placeholder)
    buf.write((mu_led * 100).round().astype('<u2').tobytes())
    buf.write((dark_wl * 10).round().astype('<u2').tobytes())
    buf.write(dark_gain.tobytes())
    # Write 2-D arrays column-major (Fortran order) to match MATLAB behaviour
    buf.write(dark_s1.flatten(order='F').tobytes())
    buf.write(dark_s2.flatten(order='F').tobytes())
    buf.write(dark_s3.flatten(order='F').tobytes())

    data = buf.getvalue()
    # Fill in calLengthBytes at offset 24
    data = data[:24] + struct.pack('<H', len(data)) + data[26:]
    with open(path, 'wb') as f:
        f.write(data)


def _write_hbb_tcal(t_cal, path):
    """Serialise a temperature calibration dict to an .hbb_tcal binary file.

    Polynomial coefficient matrix is written column-major (Fortran order) to
    match MATLAB's fwrite behaviour.
    """
    wl    = np.asarray(t_cal['wl'],    dtype=float)
    coeff = np.asarray(t_cal['coeff'], dtype='<f4')
    num_wl         = len(wl)
    polynomial_order = coeff.shape[1] - 1

    buf = io.BytesIO()
    buf.write(b'Sequoia Hyper-bb T Cal' + bytes(2))       # 24-byte ID
    buf.write(struct.pack('<H', 100))                     # processingVersion * 100
    buf.write(struct.pack('<H', 8005))                    # serialNumber
    buf.write(bytes(6))                                    # date
    buf.write(struct.pack('<H', round(t_cal.get('normalizedTemp', 20.0) * 100)))
    buf.write(struct.pack('B', polynomial_order))
    buf.write(struct.pack('B', num_wl))
    buf.write((wl * 10).round().astype('<u2').tobytes())
    buf.write(coeff.flatten(order='F').tobytes())

    with open(path, 'wb') as f:
        f.write(buf.getvalue())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHyperBBParserCreation:
    """Test HyperBBParser can be created with various configurations."""

    @_skip_if_no_cal_files()
    def test_legacy_cal_advanced_data(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced', cal_format='legacy')
        assert parser.data_format == ADVANCED_DATA_FORMAT
        assert len(parser.FRAME_VARIABLES) == 31
        assert len(parser.wavelength) > 0

    @_skip_if_no_cal_files()
    def test_legacy_cal_legacy_data(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'legacy', cal_format='legacy')
        assert parser.data_format == LEGACY_DATA_FORMAT
        assert len(parser.FRAME_VARIABLES) == 30

    @_skip_if_no_cal_files()
    def test_legacy_cal_light_data(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'light', cal_format='legacy')
        assert parser.data_format == LIGHT_DATA_FORMAT
        assert len(parser.FRAME_VARIABLES) == 14

    @_skip_if_no_cal_files()
    def test_current_binary_format(self):
        """Current format: binary .hbb_cal + .hbb_tcal files."""
        from scipy.io import loadmat
        p_mat = loadmat(PLAQUE_CAL, simplify_cells=True)['cal']
        t_mat = loadmat(TEMP_CAL,   simplify_cells=True)['cal_temp']
        with tempfile.TemporaryDirectory() as tmp:
            hbb_cal   = os.path.join(tmp, 'test.hbb_cal')
            hbb_tcal  = os.path.join(tmp, 'test.hbb_tcal')
            _write_hbb_cal(p_mat,  hbb_cal)
            _write_hbb_tcal(t_mat, hbb_tcal)
            parser = HyperBBParser(hbb_cal, hbb_tcal, 'advanced', cal_format='current')
        assert parser.data_format == ADVANCED_DATA_FORMAT
        assert len(parser.wavelength) > 0

    @_skip_if_no_cal_files()
    def test_current_cal_matches_legacy_cal(self):
        """Binary current format should yield the same calibration as legacy .mat format."""
        from scipy.io import loadmat
        p_mat = loadmat(PLAQUE_CAL, simplify_cells=True)['cal']
        t_mat = loadmat(TEMP_CAL,   simplify_cells=True)['cal_temp']
        with tempfile.TemporaryDirectory() as tmp:
            hbb_cal  = os.path.join(tmp, 'test.hbb_cal')
            hbb_tcal = os.path.join(tmp, 'test.hbb_tcal')
            _write_hbb_cal(p_mat,  hbb_cal)
            _write_hbb_tcal(t_mat, hbb_tcal)
            parser_legacy  = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced', cal_format='legacy')
            parser_current = HyperBBParser(hbb_cal, hbb_tcal, 'advanced', cal_format='current')
        np.testing.assert_array_almost_equal(parser_legacy.mu,         parser_current.mu,         decimal=4)
        np.testing.assert_array_almost_equal(parser_legacy.wavelength, parser_current.wavelength, decimal=1)

    def test_invalid_data_format_raises(self):
        with pytest.raises(ValueError, match='Data format not recognized'):
            HyperBBParser('dummy.mat', 'dummy.mat', 'invalid_format')

    def test_invalid_cal_format_raises(self):
        with pytest.raises(ValueError, match="Calibration format 'invalid' not recognized"):
            HyperBBParser('dummy.mat', 'dummy.mat', 'advanced', cal_format='invalid')

    @_skip_if_no_cal_files()
    def test_legacy_cal_without_temp_file_raises(self):
        with pytest.raises(ValueError, match='Missing temperature calibration file'):
            HyperBBParser(PLAQUE_CAL, None, 'advanced', cal_format='legacy')

    def test_current_cal_without_temp_file_raises(self):
        with pytest.raises(ValueError, match='Missing temperature calibration file'):
            # dummy .hbb_cal — error should fire before the file is read
            with tempfile.NamedTemporaryFile(suffix='.hbb_cal', delete=False) as tmp:
                tmp_path = tmp.name
            try:
                HyperBBParser(tmp_path, None, 'advanced', cal_format='current')
            finally:
                os.unlink(tmp_path)


class TestHyperBBBinaryFileReaders:
    """Verify that the binary file readers round-trip data correctly."""

    @_skip_if_no_cal_files()
    def test_plaque_cal_roundtrip(self):
        from scipy.io import loadmat
        p_mat = loadmat(PLAQUE_CAL, simplify_cells=True)['cal']
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'round.hbb_cal')
            _write_hbb_cal(p_mat, path)
            p_bin = HyperBBParser._read_binary_plaque_cal(path)
        np.testing.assert_allclose(p_bin['pmtRefGain'], p_mat['pmtRefGain'])
        np.testing.assert_allclose(p_bin['pmtGamma'],   p_mat['pmtGamma'],   rtol=1e-5)
        np.testing.assert_allclose(p_bin['gain12'],     p_mat['gain12'],     rtol=1e-3)
        np.testing.assert_allclose(p_bin['gain23'],     p_mat['gain23'],     rtol=1e-3)
        np.testing.assert_allclose(p_bin['muWavelengths'],     p_mat['muWavelengths'],     atol=0.1)
        np.testing.assert_allclose(p_bin['muFactors'],         p_mat['muFactors'],         rtol=1e-5)
        np.testing.assert_allclose(p_bin['muLedTemp'],         p_mat['muLedTemp'],         atol=0.01)
        np.testing.assert_allclose(p_bin['darkCalWavelength'], p_mat['darkCalWavelength'], atol=0.1)
        np.testing.assert_allclose(p_bin['darkCalPmtGain'],    p_mat['darkCalPmtGain'])
        np.testing.assert_allclose(p_bin['darkCalScat1'],      p_mat['darkCalScat1'],      rtol=1e-5)
        np.testing.assert_allclose(p_bin['darkCalScat2'],      p_mat['darkCalScat2'],      rtol=1e-5)
        np.testing.assert_allclose(p_bin['darkCalScat3'],      p_mat['darkCalScat3'],      rtol=1e-5)

    @_skip_if_no_cal_files()
    def test_temp_cal_roundtrip(self):
        from scipy.io import loadmat
        t_mat = loadmat(TEMP_CAL, simplify_cells=True)['cal_temp']
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'round.hbb_tcal')
            _write_hbb_tcal(t_mat, path)
            t_bin = HyperBBParser._read_binary_temp_cal(path)
        np.testing.assert_allclose(t_bin['wl'],    t_mat['wl'],    atol=0.1)
        np.testing.assert_allclose(t_bin['coeff'], t_mat['coeff'], rtol=1e-5)

    @_skip_if_no_cal_files()
    def test_plaque_cal_dark_array_orientation(self):
        """darkCalScat arrays must have shape (num_wl, num_gain) — wl as rows."""
        from scipy.io import loadmat
        p_mat = loadmat(PLAQUE_CAL, simplify_cells=True)['cal']
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'orient.hbb_cal')
            _write_hbb_cal(p_mat, path)
            p_bin = HyperBBParser._read_binary_plaque_cal(path)
        n_wl   = len(p_bin['darkCalWavelength'])
        n_gain = len(p_bin['darkCalPmtGain'])
        assert p_bin['darkCalScat1'].shape == (n_wl, n_gain)
        assert p_bin['darkCalScat2'].shape == (n_wl, n_gain)
        assert p_bin['darkCalScat3'].shape == (n_wl, n_gain)

    @_skip_if_no_cal_files()
    def test_multiple_records_returns_last(self):
        """When a .hbb_cal file contains multiple records, the last is returned."""
        from scipy.io import loadmat
        p_mat = loadmat(PLAQUE_CAL, simplify_cells=True)['cal']
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'multi.hbb_cal')
            # Write the same record twice — second should be returned
            _write_hbb_cal(p_mat, path)
            with open(path, 'rb') as f:
                first_record = f.read()
            # Modify pmtRefGain in the "second" record — PMTReferenceGain is at byte offset 42
            modified = bytearray(first_record)
            struct.pack_into('<H', modified, 42, int(p_mat['pmtRefGain']) + 1)
            with open(path, 'wb') as f:
                f.write(bytes(first_record) + bytes(modified))
            p_bin = HyperBBParser._read_binary_plaque_cal(path)
        assert p_bin['pmtRefGain'] == int(p_mat['pmtRefGain']) + 1


class TestHyperBBParserParse:
    """Test frame parsing for all data formats."""

    @_skip_if_no_cal_files()
    def test_parse_advanced_frame(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced', cal_format='legacy')
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
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'light', cal_format='legacy')
        # 14 space-separated fields
        packet = b'1 2021-01-01 12:00:00 450 2000 1000.0 100.0 90.0 80.0 36.6 20.0 10.0 12.0 0'
        data = parser.parse(packet)
        assert len(data) == len(parser.FRAME_VARIABLES)

    @_skip_if_no_cal_files()
    def test_parse_wrong_field_count_returns_empty(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced', cal_format='legacy')
        assert parser.parse(b'1 2 3') == []

    @_skip_if_no_cal_files()
    def test_parse_empty_packet_returns_empty(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced', cal_format='legacy')
        assert parser.parse(b'') == []


class TestHyperBBCalibrate:
    """Test calibration calculations."""

    @_skip_if_no_cal_files()
    def test_calibrate_advanced_single_frame(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced', cal_format='legacy')
        n = len(parser.FRAME_VARIABLES)
        raw = np.zeros((1, n))
        raw[0, parser.idx_wl]      = 450.0
        raw[0, parser.idx_PmtGain] = 2000.0
        raw[0, parser.idx_NetSig1] = 100.0
        raw[0, parser.idx_SigOn1]  = 500.0
        raw[0, parser.idx_SigOn2]  = 600.0
        raw[0, parser.idx_SigOn3]  = 700.0
        raw[0, parser.idx_SigOff1] = 400.0
        raw[0, parser.idx_SigOff2] = 500.0
        raw[0, parser.idx_SigOff3] = 600.0
        raw[0, parser.idx_RefOn]   = 1000.0
        raw[0, parser.idx_RefOff]  = 900.0
        raw[0, parser.idx_LedTemp] = 36.6
        beta_u, bb, wl, gain, net_ref_zero_flag = parser.calibrate(raw.copy())
        assert bb.shape == (1,)
        assert not np.isnan(bb[0])
        assert bb[0] > 0

    @_skip_if_no_cal_files()
    def test_calibrate_light_single_frame(self):
        parser = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'light', cal_format='legacy')
        n = len(parser.FRAME_VARIABLES)
        raw = np.zeros((1, n))
        raw[0, parser.idx_wl]          = 450.0
        raw[0, parser.idx_PmtGain]     = 2000.0
        raw[0, parser.idx_NetRef]      = 1000.0
        raw[0, parser.idx_NetSig1]     = 100.0
        raw[0, parser.idx_NetSig2]     = 90.0
        raw[0, parser.idx_NetSig3]     = 80.0
        raw[0, parser.idx_LedTemp]     = 36.6
        raw[0, parser.idx_ChSaturated] = 0
        _, bb, _, _, _ = parser.calibrate(raw.copy())
        assert not np.isnan(bb[0])
        assert bb[0] > 0

    @_skip_if_no_cal_files()
    def test_calibrate_current_binary_matches_legacy(self):
        """Binary current format should produce the same calibration output as legacy .mat."""
        from scipy.io import loadmat
        p_mat = loadmat(PLAQUE_CAL, simplify_cells=True)['cal']
        t_mat = loadmat(TEMP_CAL,   simplify_cells=True)['cal_temp']
        with tempfile.TemporaryDirectory() as tmp:
            hbb_cal  = os.path.join(tmp, 'test.hbb_cal')
            hbb_tcal = os.path.join(tmp, 'test.hbb_tcal')
            _write_hbb_cal(p_mat,  hbb_cal)
            _write_hbb_tcal(t_mat, hbb_tcal)
            parser_legacy  = HyperBBParser(PLAQUE_CAL, TEMP_CAL, 'advanced', cal_format='legacy')
            parser_current = HyperBBParser(hbb_cal, hbb_tcal, 'advanced', cal_format='current')
        n = len(parser_legacy.FRAME_VARIABLES)
        raw = np.zeros((1, n))
        raw[0, parser_legacy.idx_wl]      = 450.0
        raw[0, parser_legacy.idx_PmtGain] = 2000.0
        raw[0, parser_legacy.idx_NetSig1] = 100.0
        raw[0, parser_legacy.idx_SigOn1]  = 500.0
        raw[0, parser_legacy.idx_SigOn2]  = 600.0
        raw[0, parser_legacy.idx_SigOn3]  = 700.0
        raw[0, parser_legacy.idx_SigOff1] = 400.0
        raw[0, parser_legacy.idx_SigOff2] = 500.0
        raw[0, parser_legacy.idx_SigOff3] = 600.0
        raw[0, parser_legacy.idx_RefOn]   = 1000.0
        raw[0, parser_legacy.idx_RefOff]  = 900.0
        raw[0, parser_legacy.idx_LedTemp] = 36.6
        _, bb_legacy,  _, _, _ = parser_legacy.calibrate(raw.copy())
        _, bb_current, _, _, _ = parser_current.calibrate(raw.copy())
        np.testing.assert_array_almost_equal(bb_legacy, bb_current, decimal=4)


if __name__ == '__main__':
    import traceback
    tests = [TestHyperBBParserCreation(), TestHyperBBBinaryFileReaders(),
             TestHyperBBParserParse(), TestHyperBBCalibrate()]
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
