import os.path
import zipfile
from copy import deepcopy
from struct import pack
from threading import Lock
from time import strftime, gmtime
from collections import namedtuple

import numpy as np
import pySatlantic.instrument as pySat

from inlinino import __version__
from inlinino.log import Log, LogBinary
from inlinino.instruments import Instrument


SatPacket = namedtuple('SatlanticPacket', ['frame', 'frame_header'])


class Satlantic(Instrument):

    REQUIRED_CFG_FIELDS = ['model', 'serial_number', 'module',
                           'log_path', 'log_products',
                           'tdf_files', 'immersed']
    KEYS_TO_IGNORE = ['CRLF_TERMINATOR', 'TERMINATOR']
    KEYS_TO_NOT_DISPLAY = KEYS_TO_IGNORE + ['DATEFIELD', 'TIMEFIELD', 'CHECK_SUM']

    def __init__(self, uuid, cfg, signal, *args, **kwargs):
        if 'setup' in kwargs.keys():
            setup=kwargs['setup']
            super().__init__(uuid, cfg, signal, *args, **kwargs)
        else:
            setup=True
            super().__init__(uuid, cfg, signal, setup=False, *args, **kwargs)
        # Instrument Specific Attributes
        self._parser = None
        self.frame_headers_idx = []
        # Default serial communication parameters
        self._max_buffer_length = 2**18  # Need larger buffer for HyperNAV
        self.default_serial_baudrate = 115200  # for HyperNAV
        self.default_serial_timeout = 5
        # Init Channels to Plot Widget
        self.widget_select_channel_enabled = True
        self.widget_active_timeseries_variables_names = []
        self.widget_active_timeseries_variables_selected = []
        self.active_timeseries_variables_lock = Lock()
        self.active_timeseries_variables = {}  # dict of each frame header
        # Init Spectrum Plot Widget
        self.spectrum_plot_enabled = True
        self.spectrum_plot_axis_labels = {}
        self.spectrum_plot_trace_names = []
        self.spectrum_plot_x_values = []
        # Init Secondary Dock
        self.widget_metadata_enabled = True
        # Init Metadata Data Widget
        self.widget_metadata_keys = []
        self.widget_metadata_frame_counters = []
        # Setup
        if setup:
            self.setup(cfg)

    def setup(self, cfg):
        self.logger.debug('Setup')
        if self.alive:
            self.logger.warning('Closing port before updating connection')
            self.close()
        # Check missing fields
        for f in self.REQUIRED_CFG_FIELDS:
            if f not in cfg.keys():
                raise ValueError(f'Missing field %s' % f)
        if 'tdf_files' in cfg.keys() and 'immersed' in cfg.keys():  # Needed for child HyperNav which has custom parser
            # Parse Calibration Files
            self._parser = pySat.Instrument()
            if isinstance(cfg['tdf_files'], list):
                for f, i in zip(cfg['tdf_files'], cfg['immersed']):
                    if os.path.splitext(f)[1].lower() not in self._parser.VALID_CAL_EXTENSIONS:
                        raise pySat.CalibrationFileExtensionError(f'File extension incorrect: {f}')
                    self.logger.debug(f'Reading [immersed={i}] {f}')
                    foo = pySat.Parser(f, i)
                    self._parser.cal[foo.frame_header] = foo
                    self._parser.max_frame_header_length = max(self._parser.max_frame_header_length, len(foo.frame_header))
            elif isinstance(cfg['tdf_files'], str):
                empty_sip, i = True, 0
                archive = zipfile.ZipFile(cfg['tdf_files'], 'r')
                dirsip = os.path.join(os.path.dirname(cfg['tdf_files']),
                                      os.path.splitext(os.path.basename(cfg['tdf_files']))[0])
                if not os.path.exists(dirsip):
                    os.mkdir(dirsip)
                archive.extractall(path=dirsip)
                for f in zip(archive.namelist()):
                    if os.path.splitext(f)[1].lower() not in self._parser.VALID_CAL_EXTENSIONS \
                            or os.path.basename(f)[0] == '.':
                        continue
                    empty_sip, i = False, i + 1
                    self.logger.debug(f"Reading [immersed={cfg['immersed'][i]}] {f}")
                    foo = pySat.Parser(os.path.join(dirsip, f), cfg['immersed'][i])
                    self._parser.cal[foo.frame_header] = foo
                    self._parser.max_frame_header_length = max(self._parser.max_frame_header_length,
                                                               len(foo.frame_header))
                if empty_sip:
                    raise pySat.CalibrationFileEmptyError('No calibration file found in sip')
            else:
                raise ValueError('Expect list or str for tdf_files')
        for v in self._parser.cal.values():
            if v.baudrate is not None:
                self.default_serial_baudrate = v.baudrate
                break
        # Set Communication Interface
        self.setup_interface(cfg)
        # Set Loggers
        self.model = cfg['model']
        self.serial_number = cfg['serial_number']
        logger_cfg = {'path': cfg['log_path'], 'filename_prefix': self.bare_log_prefix}
        self._log_raw = RawLogger(logger_cfg, self.signal.status_update)
        self._log_prod = ProdLogger(logger_cfg, self._parser.cal, self._log_raw.get_file_timestamp)
        # _log_raw must be enabled in order for get_file_timestamp to work
        self.log_raw_enabled = True
        self.log_prod_enabled = cfg['log_products']
        # Update variable for Spectrum Plot
        #   updated with signal.status_update.emit()
        #   not thread safe but instrument is turned off in this function so acceptable
        self.spectrum_plot_trace_names = []
        self.spectrum_plot_x_values = []
        self.frame_headers_idx = {}
        idx = 0
        for head, cal in self._parser.cal.items():
            if cal.core_variables:
                self.spectrum_plot_trace_names.append(f'{head} {cal.core_groupname}')  # TODO Add Units
                self.spectrum_plot_x_values.append(np.array([float(cal.id[i]) for i in cal.core_variables]))
                self.frame_headers_idx[head] = idx
                idx += 1
        # TODO if no core variables disable spectrum plot widget
        # Update Active Timeseries Variables
        self.widget_active_timeseries_variables_names = []
        self.active_timeseries_variables = []
        for head, cal in self._parser.cal.items():
            self.widget_active_timeseries_variables_names += [f'{head}_{k}' for k in cal.key if k not in self.KEYS_TO_IGNORE]
            # Append middle core variable to timeseries if instruments with few wavelength
            if cal.core_variables and len(cal.core_variables) < 500:
                varnames = [f'{head}_{cal.key[cal.core_variables[int(len(cal.core_variables)/2)]]}']
            elif cal.core_variables and 'D' not in head:  # Likely light frame from HyperNAV
                wl_idx = np.argmin(np.abs(self.spectrum_plot_x_values[self.frame_headers_idx[head]] - 490))
                varnames = [f'{head}_{cal.key[cal.core_variables[wl_idx]]}']
                for k in cal.key:
                    if 'PRES' in k:
                        varnames.append(f'{head}_{k}')
            else:
                continue
            for varname in varnames:
                self.widget_active_timeseries_variables_selected.append(varname)
                self.active_timeseries_variables.append(self.active_timeseries_unpack_variable_name(varname))
        # Update Metadata Widget
        self.widget_metadata_keys = []
        self.widget_metadata_frame_counters = []
        for head, cal in self._parser.cal.items():
            if cal.core_variables:
                fields = [cal.key[i] for i in cal.auxiliary_variables if cal.key[i] not in self.KEYS_TO_NOT_DISPLAY]
            else:
                fields = [k for k in cal.key if k not in self.KEYS_TO_NOT_DISPLAY]
            self.widget_metadata_keys.append((head, fields))
            self.widget_metadata_frame_counters.append(0)
        # Update User Interface (include spectrum plot)
        self.signal.status_update.emit()  # Doesn't run on initial setup because signals are not connected

    def data_received(self, data: bytearray, timestamp: float):
        self._buffer.extend(data)
        packet = True
        while packet:
            packet, frame_header, self._buffer, unknown_bytes = self._parser.find_frame(self._buffer)
            if not packet and frame_header is None and not self._buffer and unknown_bytes:
                # No frame header found in data but need to keep data in buffer as more might be coming in
                self._buffer = unknown_bytes
                break
            if unknown_bytes:
                # Log bytes in raw files
                if self.log_raw_enabled and self._log_active:
                    self._log_raw.write(SatPacket(unknown_bytes, None), timestamp)
            if packet:
                try:
                    self.handle_packet(SatPacket(packet, frame_header), timestamp)
                except pySat.ParserError as e:
                    self.signal.packet_corrupted.emit()
                    self.logger.warning(e)
                    self.logger.debug(packet)

    def parse(self, packet: SatPacket):
        data, valid_frame = self._parser.parse_frame(packet.frame, packet.frame_header, flag_get_auxiliary_variables=True)
        if not valid_frame:
            self.signal.packet_corrupted.emit()
        return SatPacket(data, packet.frame_header)

    def handle_data(self, data: SatPacket, timestamp: float):
        cal = self._parser.cal[data.frame_header]
        # Update Metadata Widget
        metadata = [(None, None)] * len(self.frame_headers_idx)
        idx = self.frame_headers_idx[data.frame_header]
        self.widget_metadata_frame_counters[idx] += 1
        if cal.core_variables:
            values = [data.frame[cal.key[i]] for i in cal.auxiliary_variables if cal.key[i] not in self.KEYS_TO_NOT_DISPLAY]
        else:
            values = [data.frame[k] for k in cal.key if k not in self.KEYS_TO_NOT_DISPLAY]
        metadata[idx] = (self.widget_metadata_frame_counters[idx], values)
        self.signal.new_meta_data.emit(metadata)
        # Update Timeseries
        if self.active_timeseries_variables_lock.acquire(timeout=0.125):
            try:
                core_groupname = cal.core_groupname
                ts_data = [float('nan')] * len(self.active_timeseries_variables)
                for i, (frame_header, key, idx) in enumerate(self.active_timeseries_variables):
                    if frame_header == data.frame_header:
                        ts_data[i] = data.frame[key][idx] if key == core_groupname else data.frame[key]
                self.signal.new_ts_data.emit(ts_data, timestamp)
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update timeseries plot')
        # Update Spectrum Plot
        if cal.core_variables:
            spectrum_data = [None] * len(self.frame_headers_idx)
            spectrum_data[self.frame_headers_idx[data.frame_header]] = data.frame[cal.core_groupname]
            self.signal.new_spectrum_data.emit(spectrum_data)
        # Log Calibrated Data
        if self.log_prod_enabled and self._log_active:
            self._log_prod.write(data, timestamp)
            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()

    def update_active_timeseries_variables(self, name: str, state: bool):
        if not ((state and name not in self.widget_active_timeseries_variables_selected) or
                (not state and name in self.widget_active_timeseries_variables_selected)):
            return
        frame_header, key, idx = self.active_timeseries_unpack_variable_name(name)
        if self.active_timeseries_variables_lock.acquire(timeout=0.25):
            try:
                if state:
                    self.active_timeseries_variables.append((frame_header, key, idx))
                    self.widget_active_timeseries_variables_selected.append(name)
                else:
                    del self.active_timeseries_variables[self.active_timeseries_variables.index((frame_header, key, idx))]
                    del self.widget_active_timeseries_variables_selected[self.widget_active_timeseries_variables_selected.index(name)]
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update active timeseries variables')

    def active_timeseries_unpack_variable_name(self, name):
        frame_header, key, idx = *name.split('_', 1), 0
        if self._parser.cal[frame_header].core_variables and \
                key.startswith(self._parser.cal[frame_header].core_groupname):
            key, wl = key.split('_')
            idx = np.where(self.spectrum_plot_x_values[self.frame_headers_idx[frame_header]] == float(wl))[0][0]
        return frame_header, key, idx


class ProdLogger:
    """
    Log Satlantic frames calibrated, with each frame type (frame_header) in a distinct file
    Similar format as Satlantic SatCon output
    :return:
    """
    def __init__(self, log_cfg, cal, file_timestamp_getter=None):
        self.get_file_timestamp = file_timestamp_getter
        self._log = {}
        self._frame_keys = {}
        self._frame_core_var = {}
        for frame_header, v in cal.items():
            # Prepare Logger
            log_cfg['filename_suffix'] = frame_header
            log_cfg['variable_names'] = deepcopy(v.key)
            log_cfg['variable_units'] = deepcopy(v.units)
            for k in Satlantic.KEYS_TO_IGNORE:
                if k in v.key:
                    idx = v.key.index(k)
                    del log_cfg['variable_names'][idx]
                    del log_cfg['variable_units'][idx]
            # Set Frame Keys
            keys, core, precision = [], [], []
            first_flag = True
            for k, t, f in zip(v.key, v.data_type, v.fit_type):
                if v.core_variables and k.startswith(v.core_groupname):
                    if first_flag:
                        first_flag = False
                        keys.append(v.core_groupname)
                        core.append(True)
                        precision.append('%s')
                elif k not in Satlantic.KEYS_TO_IGNORE:
                    keys.append(k)
                    core.append(False)
                    # TODO Compute Precision Required from calibration file using fit_type
                    if t in ['AI', 'BU', 'BS'] and f in ['NONE', 'COUNT']:
                        precision.append('%d')
                    elif t in ['AF', 'AF16', 'BD', 'BF', 'AI', 'BU', 'BS']:  # Any fit type
                        precision.append('%.5f')
                    elif t == 'AS':
                        precision.append('%s')
                    else:
                        print(t)
            self._frame_keys[frame_header] = keys
            self._frame_core_var[frame_header] = core
            # Set logger
            log_cfg['variable_precision'] = precision
            self._log[frame_header] = Log(log_cfg)

    @property
    def filename(self) -> str:
        """
        Return filename of first logger
        :return:
        """
        for l in self._log.values():
            return l.filename

    @property
    def file_length(self):
        for l in self._log.values():
            return l.file_length

    @file_length.setter
    def file_length(self, value):
        for l in self._log.values():
            l.file_length = value

    @property
    def FILE_EXT(self) -> str:
        return Log.FILE_EXT

    def update_cfg(self, cfg: dict):
        for l in self._log.values():
            l.update_cfg(cfg)

    @staticmethod
    def format_core_variable(array):
        return np.array2string(array, separator=',', threshold=np.inf, max_line_width=np.inf)[1:-1]

    def write(self, packet: SatPacket, timestamp: float):
        if isinstance(packet.frame, list):
            data = packet.frame
        else:
            data = []
            for k, c in zip(self._frame_keys[packet.frame_header], self._frame_core_var[packet.frame_header]):
                if c:
                    data.append(self.format_core_variable(packet.frame[k]))
                else:
                    data.append(packet.frame[k])
            # values = packet.frame.values()  # Assume dictionary keep order which isn't the case with older python version
        self._log[packet.frame_header].write(data, timestamp, self.get_file_timestamp())

    def close(self):
        for l in self._log.values():
            l.close()


class RawLogger(LogBinary):
    """
    Log incoming frames as they come appending a timestamp
    Similar format as Satlantic SatView output
    No calibration applied
    :param LogBinary:
    :return:
    """
    FILE_EXT = 'raw'

    def write_header(self, values=None):
        values = dict() if values is None else values
        comment = b'Logged with Inlinino v' + __version__.encode('ASCII')
        if b'COMMENT' in values.keys():
            values[b'COMMENT'] += b'; ' + comment
        else:
            values[b'COMMENT'] = comment
        keys = [b'CRUISE-ID', b'OPERATOR', b'INVESTIGATOR', b'AFFILIATION', b'CONTACT', b'EXPERIMENT',
                b'LATITUDE', b'LONGITUDE', b'ZONE', b'CLOUD_PERCENT', b'WAVE_HEIGHT', b'WIND_SPEED', b'COMMENT',
                b'DOCUMENT', b'STATION-ID', b'CAST', b'TIME-STAMP', b'MODE', b'TIMETAG', b'DATETAG', b'TIMETAG2',
                b'PROFILER', b'REFERENCE', b'PRO-DARK', b'REF-DARK']
        header = b''
        for k in keys:
            v = values[k] if k in values.keys() else b''
            sentence = b'SATHDR ' + v + b' (' + k + b')\r\n'
            if len(sentence) > 128:
                self.__logger.warning(f'SATHDR {k} too long')
            sentence += b'\x00' * (128 - len(sentence))
            header += sentence
        self._file.write(header)

    'SATHDR  (CRUISE-ID)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (OPERATOR)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (INVESTIGATOR)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (AFFILIATION)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (CONTACT)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (EXPERIMENT)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (LATITUDE)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (LONGITUDE)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (ZONE)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (CLOUD_PERCENT)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (WAVE_HEIGHT)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (WIND_SPEED)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR Logged with Inlinino v2.8.0 (COMMENT)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (DOCUMENT)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (STATION-ID)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (CAST)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (TIME-STAMP)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (MODE)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (TIMETAG)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (DATETAG)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (TIMETAG2)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (PROFILER)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (REFERENCE)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (PRO-DARK)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00SATHDR  (REF-DARK)\r\n\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'

    @staticmethod
    def format_timestamp(timestamp: float):
        s, ms = divmod(timestamp, 1)
        return pack('!ii', int(strftime('%Y%j', gmtime(s))),
                    int('{}{:03d}'.format(strftime('%H%M%S', gmtime(s)), int(ms * 1000))))[1:]

    def write(self, packet: SatPacket, timestamp: float):
        super().write(packet.frame, timestamp)
