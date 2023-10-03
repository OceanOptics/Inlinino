import re
import os
from copy import deepcopy
from struct import unpack
from typing import Union
from time import time
from dataclasses import dataclass, field

import numpy as np
import pySatlantic.instrument as pySat

from inlinino.shared.tree import QFileItem
from inlinino.instruments import get_spy_interface, SerialInterface
from inlinino.instruments.satlantic import Satlantic, SatPacket, ProdLogger
from inlinino.app_signal import HyperNavSignals, InterfaceSignals


class HyperNav(Satlantic):
    REQUIRED_CFG_FIELDS = ['model', 'serial_number', 'module',
                           'log_path', 'log_products',
                           'prt_sbs_sn', 'sbd_sbs_sn',
                           'px_reg_path_prt', 'px_reg_path_sbd']
    CMD_TERMINATOR = b'\r\n'
    PROMPT = b'HyperNav> '

    RE_STATUS_ERROR = re.compile(b'(' + re.escape(b'$Error: ') + b'[0-9\(\)]+' + b')', re.IGNORECASE)
    RE_STATUS_OK = re.compile(b'(' + re.escape(b'$Ok') + b')', re.IGNORECASE)
    RE_IS_STATUS = re.compile(re.escape(b'$Ok') + b'|' + re.escape(b'$Error: ') + b'[0-9\(\)]+', re.IGNORECASE)
    RE_CMD_TERMINATOR = re.compile(b'(' + re.escape(b'$Ok \r\n') +
                                   b'|' + re.escape(b'$Error: ') + b'[0-9\(\)]+' + re.escape(b'\r\n') + b')',
                                   re.IGNORECASE)
    RE_IS_CMD = re.compile(b'cal|start|(?<!(?:DAQ|SLG))stop|get|set|list|dump', re.IGNORECASE)
    RE_IGNORE = re.compile(b'|'.join((re.escape(b'CMC <-'), b'Start data acquisition', b'SpecBrd', b'ERROR')))
    RE_CMD_LINE_TERMINATOR = re.compile(re.escape(CMD_TERMINATOR))  # Does not keep delimiter
    RE_CMD_CAL_START = re.compile(b'(cal|start)', re.IGNORECASE)
    # RE_CMD_START = re.compile(b'(start)', re.IGNORECASE)
    RE_CMD_STOP = re.compile(b'((?<!(?:DAQ|SLG))stop)', re.IGNORECASE)  # Ignore SLGStop or DAQStop in findall
    RE_CMD_GET = re.compile(b'(get)', re.IGNORECASE)
    RE_CMD_SET = re.compile(b'(set)', re.IGNORECASE)
    RE_CMD_LIST = re.compile(b'(list)', re.IGNORECASE)
    RE_CMD_DUMP = re.compile(b'(dump)', re.IGNORECASE)

    def __init__(self, uuid, cfg, signal: HyperNavSignals, *args, **kwargs):
        super().__init__(uuid, cfg, signal, setup=False, *args, **kwargs)
        # Custom serial interface
        self._interface = get_spy_interface(SerialInterface, echo=False)(InterfaceSignals())
        # Widget variables
        self.widget_hypernav_cal_enabled = True
        self.widget_metadata_enabled = False  # Already included in hypernav_cal widget
        self.spectrum_plot_x_label = ('', '')  # Name, Units
        self.spectrum_plot_y_label = ('signal', '')  # Name, Units
        # Special variables
        self._frame_finder = None
        self._unknown_frame_last_warn = 0
        self.default_telemetry_definition = {'SATY': hypernav_telemetry_definition(),
                                             'SATDI4': ocr504_telemetry_definition()}
        self.default_td_re_terminator = {k: re.compile(b'(' + re.escape(v.frame_terminator_bytes) + b')')
                                         for k, v in self.default_telemetry_definition.items()}
        self._parser_re_terminator = {}
        self._cmd_buffered = b''
        self._time_sent_last_cmd = 0
        self._command_mode = False  # only for interface purposes
        self._local_cfg = {'SENSTYPE': 'HyperNavRadiometer', 'SENSVERS': 'V1'}
        self.local_file_system = MapFileSystem()
        self.prt_sbs_sn = 1001
        self.sbd_sbs_sn = 1002
        self.px_reg_path = {}
        self._parser_key_map = {}
        self._parser_core_idx_limits = {}
        # Setup
        self.setup(cfg)

    def get_head_sbs_sn(self, side: str):
        return self.prt_sbs_sn if side == 'PRT' else self.sbd_sbs_sn

    @property
    def command_mode(self) -> bool:
        return self._command_mode

    @command_mode.setter
    def command_mode(self, value: bool):
        if value != self._command_mode:
            self._command_mode = value
            self.signal.toggle_command_mode.emit(value)

    def local_cfg_keys(self):
        return self._local_cfg.keys()

    def get_local_cfg(self, key: Union[bytes, str]):
        if isinstance(key, bytes):
            key = key.decode('ASCII')
        return self._local_cfg[key]

    def set_local_cfg(self, key: Union[bytes, str], value: bytes, signal=True):
        if isinstance(key, bytes):
            key = key.decode('ASCII')
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                value = value.decode('ASCII')
        self._local_cfg[key] = value
        if signal:
            self.signal.cfg_update.emit(key)
            if key in ('FRMPRTSN', 'FRMSBDSN'):
                msg = self.check_sbs_sn(key, error_on_zero=False)
                if msg:
                    self.signal.warning.emit(msg)

    def check_sbs_sn(self, head='both', error_on_zero=True):
        msg = ''
        if head in ('both', 'FRMPRTSN') and 'FRMPRTSN' in self._local_cfg.keys() and\
                self.prt_sbs_sn != self._local_cfg['FRMPRTSN'] and \
                (error_on_zero or self._local_cfg['FRMPRTSN'] != 0):
            msg += f"Port side {'serial number not matching' if self._local_cfg['FRMPRTSN'] != 0 else 'head disabled'}!\n" \
                   f"    HyperNav: FRMPRTSN={self._local_cfg['FRMPRTSN']}\n" \
                   f"    Inlinino expected {self.prt_sbs_sn}\n\n"
        if head in ('both', 'FRMSBDSN') and 'FRMSBDSN' in self._local_cfg.keys() and \
                self.sbd_sbs_sn != self._local_cfg['FRMSBDSN'] and \
                (error_on_zero or self._local_cfg['FRMSBDSN'] != 0):
            msg += f"Starboard {'serial number not matching' if self._local_cfg['FRMSBDSN'] != 0 else 'head disabled'}!\n" \
                   f"    HyperNav: FRMSBDSN={self._local_cfg['FRMSBDSN']}\n" \
                   f"    Inlinino expected {self.sbd_sbs_sn}\n\n"
        return msg[:-1]

    def set_frame_finder(self):
        self._frame_finder = re.compile(b'(' + b'|'.join(
            [re.escape(k.encode('ASCII')) for k in self._parser.cal.keys()] +
            [re.escape(self.PROMPT)] +
            [re.escape(k.encode('ASCII')) for k in ('SATYLZ', 'SATYDZ', 'SATYCZ', 'SATDI4')]
        ) + b')')
        self._parser_re_terminator = {}
        for k, p in self._parser.cal.items():
            self._parser_re_terminator[k] = re.compile(b'(' + re.escape(p.frame_terminator_bytes) + b')')

    def send_cmd(self, cmd: str, check_timing=True):
        """
        Write command (cmd) to interface
        :param cmd: command to send
        :param check_timing:
        :return:
        """
        if not self.alive:
            self.signal.warning.emit('Instrument must be connected before sending commands.')
            return False
        if check_timing and time() - self._time_sent_last_cmd < 0.5:
            self.signal.warning.emit('Wait at least one second between command transmission.')
            return False
        self._interface.write(f'{cmd}\r\n'.encode('utf8', errors='replace'))
        self._time_sent_last_cmd = time()
        return True

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
        pixel_reg_type, cal_signal = [], []
        for head, path, sn in zip(['prt', 'sbd'],
                                  ['px_reg_path_prt', 'px_reg_path_sbd'],
                                  [self.prt_sbs_sn, self.sbd_sbs_sn]):
            if path not in cfg.keys():
                continue
            if not cfg[path]:
                td = hypernav_telemetry_definition()
                pixel_reg_type.append('channel')
                cal_signal.append(False)
            elif os.path.splitext(cfg[path])[1] == '.cgs':
                px_reg = [f'{wl:.2f}' for wl in read_manufacturer_pixel_registration(cfg[path])]
                td = hypernav_telemetry_definition(px_reg)
                pixel_reg_type.append('wavelength')
                cal_signal.append(False)
            elif os.path.splitext(cfg[path])[1] in self._parser.VALID_CAL_EXTENSIONS:
                td = pySat.Parser(cfg[path])
                td.frame_nfields = len(td.type) - (1 if td.type[-1] == 'TERMINATOR' else 0)
                pixel_reg_type.append('wavelength')
                cal_signal.append(True)
            else:
                raise pySat.CalibrationFileExtensionError(f'File extension incorrect: {cfg[path]}')
            td.frame_header = f'SATYLZ{sn:04d}'
            self._parser.cal[td.frame_header] = td
            td = deepcopy(td)
            td.frame_header = f'SATYDZ{sn:04d}'
            self._parser.cal[td.frame_header] = td
            self._parser.max_frame_header_length = max(self._parser.max_frame_header_length, len(td.frame_header))
        # Build frame finder pattern
        self.set_frame_finder()
        # Spectral Plot X Label
        if 'wavelength' in pixel_reg_type and 'channel' in pixel_reg_type:
            self.spectrum_plot_x_label = ('Channel | Wavelength', '# | nm')
        elif 'wavelength' in pixel_reg_type:
            self.spectrum_plot_x_label = ('Wavelength', 'nm')
        else:
            self.spectrum_plot_x_label = ('Channel', '#')
        # Spectral Plot Y Label
        if True in cal_signal and False in cal_signal:
            self.spectrum_plot_y_label = ('Lu', 'counts | uW/cm2/nm/sr')
        elif True in cal_signal:
            self.spectrum_plot_y_label = ('Lu', 'uW/cm2/nm/sr')
        else:
            self.spectrum_plot_y_label = ('Lu', 'counts')
        # Map keys
        for k, p in self._parser.cal.items():
            self._parser_key_map[k] = self.map_key_to_idx(p.key)
            self._parser_core_idx_limits[k] = (min(p.core_variables), max(p.core_variables)+1)
        # Setup as regular Satlantic instrument
        super().setup(cfg)
        # Change default file length to one day
        self._log_raw.file_length = 24 * 60 * 60  # seconds
        self._log_prod.file_length = self._log_raw.file_length

    def data_received(self, data: bytearray, timestamp: float):
        self._buffer.extend(data)
        # Find Frames (added prompt as frame header to find command)
        frames = self._frame_finder.split(self._buffer)
        if len(frames) < 2:  # No frame found
            return
        if len(frames[0]):  # No header for first frame (command or unknown bytes)
            if not self.parse_cmd(frames[0]):  # Attempt to parse command (e.g. stop during acquisition mode)
                self.signal.packet_corrupted.emit()
            if self.log_raw_enabled and self._log_active:
                self._log_raw.write(SatPacket(frames[0], None), timestamp)
        headers = frames[1::2]
        frames = frames[2::2]
        # Check Complete last frame
        if headers[-1] == self.PROMPT:
            try:
                if self.RE_CMD_DUMP.match(frames[-1]):
                    # Special command `dump` will typically be incomplete due to volume of data sent
                    #   Keep all buffer in last frame
                    self._buffer = bytearray()
                else:
                    # Complete last frame
                    f, sep, b = self.RE_CMD_TERMINATOR.split(frames[-1], 1)
                    frames[-1], self._buffer = f + sep, bytearray(b)
            except ValueError:
                # Incomplete last frame
                self._buffer = self._buffer[-len(headers[-1]) - len(frames[-1]):]
                del headers[-1], frames[-1]
        else:
            header_decoded = headers[-1].decode()
            try:
                # Known Headers
                parser, re_terminator = self._parser.cal[header_decoded], self._parser_re_terminator[header_decoded]
            except KeyError:
                # Default Headers
                try:
                    parser = self.default_telemetry_definition[header_decoded]
                    re_terminator = self.default_td_re_terminator[header_decoded]
                except KeyError:
                    parser = self.default_telemetry_definition['SATY']
                    re_terminator = self.default_td_re_terminator['SATY']
            if parser.variable_frame_length:
                try:
                    f, sep, b = re_terminator.split(frames[-1], 1)
                    frames[-1], self._buffer = f + sep, bytearray(b)
                except ValueError:
                    self._buffer = self._buffer[-len(headers[-1]) - len(frames[-1]):]
                    del headers[-1], frames[-1]
            else:
                if len(frames[-1]) < parser.frame_length:
                    self._buffer = self._buffer[-len(headers[-1]) - len(frames[-1]):]
                    del headers[-1], frames[-1]
                elif len(frames[-1]) > parser.frame_length:
                    self._buffer = frames[-1][parser.frame_length:]
                    frames[-1] = frames[-1][:parser.frame_length]
        # Dispatch frames
        for header, frame in zip(headers, frames):
            header_decoded = header.decode()
            if header == self.PROMPT:  # Handle Command
                if self.log_raw_enabled and self._log_active:
                    self._log_raw.write(SatPacket(header+frame, header_decoded), timestamp)
                self.parse_cmd(frame)
            elif header_decoded in self._parser.cal.keys():  # Handle Known Data Frame
                try:
                    self.handle_packet(SatPacket(header+frame, header_decoded), timestamp)
                except Exception as e:
                    self.signal.packet_corrupted.emit()
                    self.logger.warning(e)
                    self.logger.debug(header+frame)
                    # raise e
            else:  # Handle Unknown Data Frame
                if self.log_raw_enabled and self._log_active:
                    self._log_raw.write(SatPacket(header+frame, header_decoded), timestamp)
                if time() - self._unknown_frame_last_warn > 60:
                    self._unknown_frame_last_warn = time()
                    self.signal.warning.emit(f'HyperNav data {header + frame[:4]} not displayed '
                                             f'due to inconsistent serial number. '
                                             f'Please update HyperNav configuration (Control Tab>Sampled Spec.) '
                                             f'or Inlinino configuration (Setup Button>SBS SN).')

    def parse_cmd(self, response):
        """
        Parse command response
        :param response: bytearray containing prompt, command, and response (without delimiter $Ok)
        :return: status True: ok | False: error
        """
        # Special command `dump`
        if self.RE_CMD_DUMP.match(response):
            self.download(response)
            return True
        # Break into lines
        lines = self.RE_CMD_LINE_TERMINATOR.split(response)
        # Clean Response
        ll = []
        for l in lines:
            if l:
                if self.RE_IGNORE.match(l):
                    cmds = self.RE_IS_CMD.findall(l)
                    if cmds:
                        ll.append(cmds[-1] + l.split(cmds[-1], 1)[-1])
                else:
                    ll.append(l)
        lines[:] = ll
        # Validate Response
        if len(lines) == 0:  # Ignored all input
            return True
        cmd, status = lines[0], lines[-1]
        if len(lines) < 2:  # Only one line
            if self.RE_IS_CMD.match(lines[0]):
                self._cmd_buffered = lines[0]
                return True
            elif self.RE_IS_STATUS.match(lines[0]) and self._cmd_buffered:
                cmd, status = self._cmd_buffered, lines[0]
            else:
                self.logger.warning(f'Command {lines[0]} return no status.')
                return False
        self._cmd_buffered = b''  # Empty cmd buffered
        if self.RE_STATUS_ERROR.match(status):
            self.logger.warning(f'Command error: {status}')
            return False
        if not self.RE_STATUS_OK.match(status) and not self.RE_CMD_DUMP.match(cmd):
            self.logger.warning(f'Command response unexpected: {status}')
            return False
        # Handle Command
        if self.RE_CMD_CAL_START.match(cmd):
            self.command_mode = False
        elif self.RE_CMD_STOP.match(cmd):
            self.command_mode = True
        elif self.RE_CMD_GET.match(cmd):
            param = cmd[3:].strip()
            if param == b'cfg':
                # Parse configuration
                for l in lines[1:-1]:
                    try:
                        self.set_local_cfg(*l.strip().split(b' '), signal=False)
                    except TypeError:  # Blank lines
                        pass
                self.signal.cfg_update.emit('*')
                msg = self.check_sbs_sn(error_on_zero=False)
                if msg:
                    self.signal.warning.emit(msg)
            else:
                value = status[3:].strip()
                self.set_local_cfg(param, value)
        elif self.RE_CMD_SET.match(cmd):
            self.set_local_cfg(*cmd[3:].strip().split(b' '))
        elif self.RE_CMD_LIST.match(cmd):
            if not lines[1].startswith(b'DIR name is'):
                self.signal.warning.emit(f'Invalid absolute path: {lines[1]}')
                return False
            self.local_file_system.add_files(
                abs_path=lines[1].decode('ASCII').rsplit(' ', 1)[1],
                files=[l.decode('ASCII') for l in lines[3:-2]]  # Skip abs_path line, header line, total item listed line, blank line
            )
            self.signal.cmd_list.emit()
        else:
            self.logger.warning(f'Command {cmd} not supported by Inlinino.')
            return False
        return True

    def download(self, response):
        """
        Takes over interface to read data directly
            blocking self._run

        :return:
        """
        try:
            # Get command line
            while True:
                lines = response.split(HyperNav.CMD_TERMINATOR, 1)
                if len(lines) == 2:  # Received complete command line
                    cmd, rx = lines
                    break
                response += self._interface.read()
            # Read data
            if b'$' in rx:  # All data in command response
                data_hex, self._buffer = rx.split(b'$', 1)
            else:  # Read more data
                # Disable spy interface timeout
                timeout = self._interface.timeout
                self._interface.timeout = None
                self._interface.spy_enabled = False
                # Read data until dump is complete
                data_hex = self._interface.read_until(b'$')  # This command must run
                # Re-enable interface timeout
                self._interface.spy_enabled = True
                self._interface.timeout = timeout
                # Log data received
                if self.log_raw_enabled and self._log_active:
                    self._log_raw.write(SatPacket(data_hex, None), timestamp=None)
                # Concatenate data
                data_hex = rx + data_hex[:-1]
            # Get remote path & create local directories
            args = cmd.strip().split(b' ')
            remote_path = args[2].decode('ASCII').strip(' 0:\\').split(self.local_file_system.SEP)
            local_path = os.path.join(self._log_raw.path, *remote_path[:-1])
            os.makedirs(local_path, exist_ok=True)
            # Write to file
            filename = os.path.join(local_path, remote_path[-1])
            with open(filename, 'wb') as f:
                data_bin = bytearray.fromhex(data_hex.replace(b' ', b'').decode())
                f.write(data_bin)
            # Signal download is over
            self.signal.cmd_dump.emit(len(data_bin))
        except Exception as e:
            self.logger.warning(e)
            self.signal.cmd_dump.emit(-2)
            self.signal.warning.emit(f'An error occured while downloading file:\n{e}\n')

    def parse(self, packet: SatPacket):
        """
        Dynamic parser (doesn't require head serial number)
        Does NOT apply calibration
        :param packet:
        :return:
        """
        try:
            parser = self._parser.cal[packet.frame_header]
        except KeyError:
            raise pySat.ParserError(f"Missing cal/tdf for frame header {packet.frame_header}.")
        if parser.variable_frame_length:
            try:
                data = packet.frame[11:].decode(self._parser.ENCODING).strip('\r\n').split(',')
            except UnicodeDecodeError:
                # Invalid frame (in SatView format), likely truncated by another frame
                raise pySat.ParserError(f"Failed to decode frame {packet.frame_header}.")
            if len(data) != parser.frame_nfields:
                raise pySat.ParserError(f"Invalid number of fields in {packet.frame_header}.")
        else:
            data = unpack(parser.frame_fmt, packet.frame[10:])
        try:
            if 'AI' in parser.data_type or 'AF' in parser.data_type:
                data = [int(v) if t == 'AI' else
                        float(v) if t == 'AF' else v
                        for v, t in zip(data, parser.data_type)]
        except ValueError:
            raise pySat.ParserError(f"Unexpected data type in {packet.frame_header}.")
        return SatPacket(data, packet.frame_header)

    def handle_data(self, data: SatPacket, timestamp: float):
        # Needed to overwrite handle_data has data format changed from calibrated dict to raw list.
        cal = self._parser.cal[data.frame_header]
        # Update Metadata Widget
        metadata = [(None, None)] * len(self.frame_headers_idx)
        idx = self.frame_headers_idx[data.frame_header]
        self.widget_metadata_frame_counters[idx] += 1
        values = [data.frame[i] for i in cal.auxiliary_variables if cal.key[i] not in self.KEYS_TO_NOT_DISPLAY]
        metadata[idx] = (self.widget_metadata_frame_counters[idx], values)
        self.signal.new_meta_data.emit(metadata)
        # Get Integration Time
        if cal.cal_coefs:
            i = cal.type.index('INTTIME')
            aint = self._parser._fit_data(data.frame[i], cal.fit_type[i], cal.cal_coefs[i])
        # Update Timeseries
        if self.active_timeseries_variables_lock.acquire(timeout=0.125):
            try:
                ts_data = [float('nan')] * len(self.active_timeseries_variables)
                for i, (frame_header, key, idx) in enumerate(self.active_timeseries_variables):
                    if frame_header == data.frame_header:
                        if cal.cal_coefs:
                            ts_data[i] = self._parser._fit_data(data.frame[idx], cal.fit_type[idx], cal.cal_coefs[idx], aint)
                        else:
                            ts_data[i] = data.frame[idx]
                self.signal.new_ts_data.emit(ts_data, timestamp)
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update timeseries plot')
        # Update Spectrum Plot
        spectrum_data = [None] * len(self.frame_headers_idx)
        idx_start, idx_end = self._parser_core_idx_limits[data.frame_header]
        spectra = np.array(data.frame[idx_start:idx_end])
        if cal.core_cal_coefs is not None and len(cal.core_cal_coefs[0]) == len(spectra):  # OPTIC3 calibration (not immersed)
            spectrum_data[self.frame_headers_idx[data.frame_header]] = (
                    cal.core_cal_coefs[1, :] * (spectra - cal.core_cal_coefs[0, :]) * aint / cal.core_cal_coefs[3, :])
        else:
            spectrum_data[self.frame_headers_idx[data.frame_header]] = spectra
        self.signal.new_spectrum_data.emit(spectrum_data)
        # Update Calibration Widget
        self.signal.new_frame.emit(data)
        # Log Parsed Data
        if self.log_prod_enabled and self._log_active:
            self._log_prod.write(SatPacket(
                [*data.frame[:idx_start], ProdLogger.format_core_variable(spectra), *data.frame[idx_end:]],
                data.frame_header
            ), timestamp)
            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()

    @staticmethod
    def map_key_to_idx(keys):
        return {k: i for i, k in enumerate(keys)}

    def active_timeseries_unpack_variable_name(self, name):
        frame_header, key = name.split('_', 1)
        idx = self._parser_key_map[frame_header][key]
        return frame_header, key, idx


class MapFileSystem:
    ROOT = '0:'
    SEP = r'\\'
    CASE_SENSITIVE = True

    def __init__(self, root: str = '0:'):
        self.fs = QFileItem(root, True)

    def reset(self):
        self.fs = QFileItem(MapFileSystem.ROOT, True)

    def walk(self, abs_path: str, strict=True):
        abs_path = (abs_path.lower() if MapFileSystem.CASE_SENSITIVE else abs_path).split(MapFileSystem.SEP)
        cwd = self.fs
        for file_name in abs_path[1:]:
            for d in cwd.files:
                if file_name == d.name:
                    if not d.is_dir:
                        raise ValueError(f'Not a directory: {file_name}')
                    cwd = d
                    break
            else:
                if strict:
                    raise ValueError(f'No such file or directory: {file_name}')
                else:
                    cwd.addChild(QFileItem(file_name, True))
        return cwd

    def add_files(self, abs_path: str, files: list):
        cwd = self.walk(abs_path, strict=False)
        cwd.add_files([QFileItem.from_line(f.lower() if MapFileSystem.CASE_SENSITIVE else f) for f in files])

    def explore(self, cwd=None, level=1):
        """
        Return folder to list until all directories within the level specified are explored
        :param cwd: current working directory
        :param level: level to explore
        :return:
        """
        if cwd is None:
            cwd = self.fs
        if cwd.is_dir and not cwd.is_listed:
            return cwd.name
        if level > 0:
            for child in cwd.files:
                explore = self.explore(child, level-1)
                if explore is not None:
                    return cwd.name + MapFileSystem.SEP + explore
        return None

    def join(self, *args):
        return MapFileSystem.SEP.join(args)


def hypernav_telemetry_definition(pixel_registration=None):
    """
    HyperNAV Telemetry Definition
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
    satx_z.fit_type = ['COUNT', 'COUNT', 'COUNT', 'COUNT', 'COUNT', 'COUNT', 'COUNT', 'COUNT',
                       'POLYU', 'POLYU', 'COUNT', 'COUNT', 'COUNT', 'COUNT', 'POLYU', 'POLYU',
                       'POLYU', 'POLYU', 'POLYU', 'POLYU', 'COUNT'] + ['OPTIC3'] * n_pixel + ['COUNT']
    satx_z.core_variables = [i for i, t in enumerate(satx_z.type) if t == 'LU']
    satx_z.core_groupname = 'LU'
    satx_z.auxiliary_variables = [i for i, x in enumerate(satx_z.type) if x.upper() != satx_z.core_groupname]
    satx_z.variable_frame_length = False
    satx_z.frame_nfields = len(satx_z.type)
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
    saty_z.field_separator = [','] * satx_z.frame_nfields + ['\r\n']
    saty_z.data_type = ['AI', 'AF', 'AI', 'AI', 'AI', 'AI', 'AI', 'AI',
                        'AI', 'AI', 'AI', 'AI', 'AI', 'AI', 'AI', 'AI',
                        'AI', 'AI', 'AI', 'AI', 'AS'] + ['AI'] * n_pixel + ['AI', 'AS']
    saty_z.check_cum_index = None
    saty_z.frame_terminator = '\r\n'
    saty_z.frame_terminator_bytes = b'\x0D\x0A'
    return saty_z


def ocr504_telemetry_definition():
    """
    OCR 504 Telemetry Definition
    :return:
    """
    satdi4 = pySat.Parser()
    satdi4.frame_header = 'SATDI4'
    satdi4.frame_header_length = 10
    satdi4.core_groupname, n_pixel = 'E?', 4
    satdi4.type = ['TIMER', 'DELAY'] + [satdi4.core_groupname] * n_pixel + \
                  ['VS', 'TEMP', 'FRAME', 'CHECK', 'CRLF']
    satdi4.id = ['NONE', 'SAMPLE'] + [f'{x}' for x in range(n_pixel)] + \
                ['NONE', 'PCB', 'COUNTER', 'SUM', 'TERMINATOR']
    satdi4.key = [t if i == 'NONE' else f'{t}_{i}' for t, i in zip(satdi4.type, satdi4.id)]
    satdi4.data_type = ['AF', 'BS'] + ['BU'] * n_pixel + ['BU', 'BU', 'BU', 'BU', 'BU']
    satdi4.fit_type = ['COUNT', 'COUNT'] + ['OPTIC2'] * n_pixel + ['POLYU', 'POLYU', 'COUNT', 'COUNT', 'NONE']
    satdi4.core_variables = [i for i, t in enumerate(satdi4.type) if t == satdi4.core_groupname]
    satdi4.auxiliary_variables = [i for i, x in enumerate(satdi4.type) if x.upper() != satdi4.core_groupname]
    satdi4.variable_frame_length = False
    satdi4.frame_length = 46
    satdi4.frame_fmt = '!10sh' + 'I' * n_pixel + 'HHBBH'
    satdi4.check_sum_index = -3
    satdi4.frame_terminator = '\r\n'
    satdi4.frame_terminator_bytes = b'\x0D\x0A'
    return satdi4


def read_manufacturer_pixel_registration(filename):
    """
    Read coefficients from manufacturer (.cgs file) and compute pixel registration
    # DUPLICATED FUNCTION from hypernav.calibrate.wavelength_registration to avoid import from hypernav library
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

