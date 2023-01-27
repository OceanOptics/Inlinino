import os
from copy import deepcopy
from struct import unpack

import numpy as np
import pySatlantic.instrument as pySat

from inlinino.instruments import get_spy_interface, SerialInterface
from inlinino.instruments.satlantic import Satlantic, SatPacket
from inlinino.signal import HyperNavSignals, InterfaceSignals


class HyperNav(Satlantic):
    REQUIRED_CFG_FIELDS = ['model', 'serial_number', 'module',
                           'log_path', 'log_products',
                           'prt_sbs_sn', 'sbd_sbs_sn',
                           'px_reg_path_prt', 'px_reg_path_sbd']

    def __init__(self, uuid, signal: HyperNavSignals, *args, **kwargs):
        super().__init__(uuid, signal, setup=False, *args, **kwargs)
        self._interface = get_spy_interface(SerialInterface)(InterfaceSignals())
        self.plugin_hypernav_cal_enabled = True
        # Special variables
        self.mirror_hn_cfg = {'SENSTYPE': 'HyperNavRadiometer', 'SENSVERS': 'V1'}
        self._command_mode = False
        # self.prt_zeiss_sn = None
        # self.sbd_zeiss_sn = None
        self.prt_sbs_sn = 1001
        self.sbd_sbs_sn = 1002
        self.px_reg_path = {}
        self._parser_key_map = {}
        self._parser_core_idx_limits = {}
        # Setup
        self.init_setup()

    def get_head_sbs_sn(self, side: str):
        return self.prt_sbs_sn if side == 'PRT' else self.sbd_sbs_sn

    @property
    def command_mode(self) -> bool:
        return self._command_mode

    @command_mode.setter
    def command_mode(self, value: bool):
        if value != self._command_mode:
            self._command_mode = value
            self.signal.toggle_command_mode(value)

    def interface_write(self, data: bytes):
        self._interface.write(data)

    def setup(self, cfg):
        # Get serial numbers
        if 'prt_sbs_sn' in cfg.keys():
            self.prt_sbs_sn = int(cfg['prt_sbs_sn'])
        if 'sbd_sbs_sn' in cfg.keys():
            self.sbd_sbs_sn = int(cfg['sbd_sbs_sn'])
        if 'px_reg_path_prt' in cfg.keys() and 'px_reg_path_sbd':
            self.px_reg_path = {'PRT': cfg['px_reg_path_prt'], 'SBD': cfg['px_reg_path_sbd']}
        # Get HyperNav  specific parser with appropriate pixel registration
        self._parser = pySat.Instrument()
        for head, path, sn in zip(['prt', 'sbd'],
                                  ['px_reg_path_prt', 'px_reg_path_sbd'],
                                  [self.prt_sbs_sn, self.sbd_sbs_sn]):
            if path not in cfg.keys():
                continue
            if not cfg[path]:
                td = hypernav_telemetry_definition()
            elif os.path.splitext(cfg[path])[1] == '.cgs':
                px_reg = [f'{wl:.2f}' for wl in read_manufacturer_pixel_registration(cfg[path])]
                td = hypernav_telemetry_definition(px_reg)
            elif os.path.splitext(cfg[path])[1] in self._parser.VALID_CAL_EXTENSIONS:
                td = pySat.Parser(cfg[path])
            else:
                raise pySat.CalibrationFileExtensionError(f'File extension incorrect: {cfg[path]}')
            td.frame_header = f'SATYLZ{sn:04d}'
            self._parser.cal[td.frame_header] = td
            td = deepcopy(td)
            td.frame_header = f'SATYDZ{sn:04d}'
            self._parser.cal[td.frame_header] = td
            self._parser.max_frame_header_length = max(self._parser.max_frame_header_length, len(td.frame_header))
        # Map keys
        for k, p in self._parser.cal.items():
            self._parser_key_map[k] = self.map_key_to_idx(p.key)
            self._parser_core_idx_limits[k] = (min(p.core_variables), max(p.core_variables)+1)
        # Setup as regular Satlantic instrument
        super().setup(cfg)

    def parse(self, packet: SatPacket):
        """
        Dynamic parser (doesn't require head serial number)
        Does NOT apply calibration
        :param packet:
        :return:
        """
        try:
            parser = self._parser.cal[packet.frame_header]
            if parser.variable_frame_length:
                try:
                    data = packet.frame[11:].decode(self._parser.ENCODING).strip('\r\n').split(',')
                except UnicodeDecodeError:
                    # Invalid frame (in SatView format), likely truncated by another frame
                    raise pySat.ParserError(f"Failed to decode frame {packet.frame[11:]}.")
            else:
                data = unpack(parser.frame_fmt, packet.frame[10:])
            if 'AI' in parser.data_type or 'AF' in parser.data_type:
                data = [int(v) if t == 'AI' else
                        float(v) if t == 'AF' else v
                        for v, t in zip(data, parser.data_type)]
            frame_header = packet.frame[:10].decode(self._parser.ENCODING)
            return SatPacket(data, frame_header)
        except pySat.ParserError as e:
            self.signal.packet_corrupted.emit()
            self.logger.warning(e)
            self.logger.debug(packet)

    def handle_data(self, data: SatPacket, timestamp: float):
        # Need to overwritte handle_data has data format changed from calibrated dict to raw list.
        cal = self._parser.cal[data.frame_header]
        # Update Metadata Plugin
        metadata = [(None, None)] * len(self.frame_headers_idx)
        idx = self.frame_headers_idx[data.frame_header]
        self.plugin_metadata_frame_counters[idx] += 1
        values = [data.frame[i] for i in cal.auxiliary_variables if cal.key[i] not in self.KEYS_TO_NOT_DISPLAY]
        metadata[idx] = (self.plugin_metadata_frame_counters[idx], values)
        self.signal.new_meta_data.emit(metadata)
        # Update Timeseries
        if self.active_timeseries_variables_lock.acquire(timeout=0.125):
            try:
                ts_data = [float('nan')] * len(self.active_timeseries_variables)
                for i, (frame_header, key, idx) in enumerate(self.active_timeseries_variables):
                    if frame_header == data.frame_header:
                        ts_data[i] = data.frame[idx]
                self.signal.new_ts_data.emit(ts_data, timestamp)
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update timeseries plot')
        # Update Spectrum Plot
        spectrum_data = [None] * len(self.frame_headers_idx)
        idx_start, idx_end = self._parser_core_idx_limits[data.frame_header]
        spectrum_data[self.frame_headers_idx[data.frame_header]] = np.array(data.frame[idx_start:idx_end])
        self.signal.new_spectrum_data.emit(spectrum_data)
        # Update Calibration Plugin
        self.signal.new_frame.emit(data)
        # Log Parsed Data
        if self.log_prod_enabled and self._log_active:
            self._log_prod.write(data, timestamp)
            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()

    @staticmethod
    def map_key_to_idx(keys):
        return {k: i for i, k in enumerate(keys)}

    def active_timeseries_unpack_variable_name(self, name):
        frame_header, key = name.split('_', 1)
        idx = self._parser_key_map[frame_header][key]
        return frame_header, key, idx


def hypernav_telemetry_definition(pixel_registration=None):
    """
    HyperNAV Telemetry Definition (without calibration)
    :return:
    """
    n_pixel = 2048
    if pixel_registration is None:
        pixel_registration = [f'{x}' for x in range(n_pixel)]
    elif len(pixel_registration) != 2048:
        raise ValueError('Unexpected pixel registration length, expected 2048.')
    # Lu Fixed Length (binary)
    satx_z = pySat.Parser()
    satx_z.frame_header = 'SATX_Z'
    satx_z.frame_header_length = 10
    satx_z.type = ['DATEFIELD', 'TIMEFIELD', 'SIDE', 'SAMPLE', 'INTTIME', 'DARK_AVE', 'DARK_SDV', 'SHIFTUP',
                   'TEMP_SPEC', 'PRES', 'PT_COUNT', 'PT_DURAT', 'PP_COUNT', 'PP_DURAT', 'SUNAZIMUTH', 'HEADING',
                   'TILT', 'TILT', 'OTHER_TILT', 'OTHER_TILT', 'TAG'] + ['LU'] * n_pixel + ['CHECK']
    satx_z.id = ['NONE', 'NONE', 'NONE', 'NONE', 'LU', 'NONE', 'NONE', 'NONE', 'NONE', 'NONE', 'NONE', 'NONE',
                 'NONE', 'NONE', 'NONE', 'NONE', 'Y', 'X', 'Y', 'X', 'NONE'] + pixel_registration + \
                ['SUM']
    satx_z.key = [t if i == 'NONE' else f'{t}_{i}' for t, i in zip(satx_z.type, satx_z.id)]
    satx_z.units = ['YYYYDDD', 'HH.hhhhhh', '', '', 'sec', '', '', '', 'c', 'm', '', '', '', '', 'degree', 'degree',
                    'degree', 'degree', 'degree', 'degree', ''] + ['uW/cm^2/nm/sr'] * n_pixel + ['']
    satx_z.data_type = ['BS', 'BD', 'BU', 'BU', 'BU', 'BU', 'BU', 'BU',
                        'BS', 'BS', 'BS', 'BU', 'BS', 'BU', 'BS', 'BS',
                        'BS', 'BS', 'BS', 'BS', 'BU'] + ['BU'] * n_pixel + ['BU']
    satx_z.core_variables = [i for i, t in enumerate(satx_z.type) if t == 'LU']
    satx_z.core_groupname = 'LU'
    satx_z.auxiliary_variables = [i for i, x in enumerate(satx_z.type) if x.upper() != satx_z.core_groupname]
    satx_z.variable_frame_length = False
    satx_z.frame_length = 4169
    satx_z.frame_fmt = '!idHHHHHHhiiIiIhhhhhhI' + 'H' * n_pixel + 'B'
    satx_z.check_sum_index = -1
    # Lu Variable length (ascii)
    saty_z = deepcopy(satx_z)
    saty_z.frame_header = 'SATY_Z'
    saty_z.type.append('TERMINATOR')
    saty_z.id.append('NONE')
    saty_z.key.append('TERMINATOR')
    saty_z.units.append('')
    # TERMINATOR is NOT added to auxiliary_variables
    saty_z.variable_frame_length = True
    saty_z.field_separator = [','] * 2070 + ['\r\n']
    saty_z.data_type = ['AI', 'AF', 'AI', 'AI', 'AI', 'AI', 'AI', 'AI', 'AI', 'AI', 'AI', 'AI', 'AI', 'AI', 'AI',
                        'AI', 'AI', 'AI', 'AI', 'AI', 'AS'] + ['AI'] * n_pixel + ['AI', 'AS']
    saty_z.check_cum_index = None
    saty_z.frame_terminator = '\r\n'
    saty_z.frame_terminator_bytes = b'\x0D\x0A'
    return saty_z


def read_manufacturer_pixel_registration(filename):
    """
    Read coefficients from manufacturer (.cgs file) and compute pixel registration
    :param filename:
    :return:
    """
    c = [float('nan')] * 4
    with open(filename, 'r') as f:
        for l in f:
            if len(l) < 3:
                continue
            if l[0] == 'C' and l[1].isdigit() and l[2] == ' ':
                c[int(l[1])] = float(l.split(' ')[1])
    if np.any(np.isnan(c)):
        raise ValueError(f'Missing coefficients in {filename} file.')
    x = np.arange(2058, 10, -1)
    return c[0] + c[1] * x + c[2] * x ** 2 + c[3] * x ** 3

