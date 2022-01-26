import os.path
import zipfile
from copy import deepcopy
from struct import pack
from threading import Lock
from time import strftime, gmtime
from collections import namedtuple

import numpy as np
import pyqtgraph as pg
import pySatlantic.instrument as pySat

from inlinino import COLOR_SET, __version__
from inlinino.log import Log, LogBinary
from inlinino.instruments import Instrument


PacketMaker = namedtuple('SatlanticPacket', ['frame', 'frame_header'])


class Satlantic(Instrument):

    REQUIRED_CFG_FIELDS = ['model', 'serial_number', 'module',
                           'log_path', 'log_products',
                           'tdf_files', 'immersed']
    KEYS_TO_IGNORE = ['CRLF_TERMINATOR', 'TERMINATOR']

    def __init__(self, cfg_id, signal, *args, **kwargs):
        self._parser = None

        # Init Core Variable Graphic
        pg.setConfigOption('background', '#F8F8F2')
        pg.setConfigOption('foreground', '#26292C')
        self._pw = pg.plot(enableMenu=False)
        self._pw.setWindowTitle('Satlantic Spectrum')
        self._plot = self._pw.plotItem
        self._plot.addLegend()
        self._plot.setLabel('bottom', 'Wavelength', units='nm')
        self._plot.setLabel('left', 'Signal', units='SI')
        self._plot.setMouseEnabled(x=False, y=True)
        self._plot.showGrid(x=True, y=True)
        self._plot.enableAutoRange(x=True, y=True)
        self._plot.getAxis('left').enableAutoSIPrefix(False)
        self._plot_curves = {}
        self.wavelengths = {}

        # Default serial communication parameters
        self.default_serial_baudrate = 57600
        self.default_serial_timeout = 5

        # Init Channels to Plot Plugin
        self.plugin_active_timeseries_variables_names = []
        self.plugin_active_timeseries_variables_selected = []
        self.active_timeseries_variables_lock = Lock()
        self.active_timeseries_variables = {}  # dict of each frame header

        super().__init__(cfg_id, signal, *args, **kwargs)

        # Satlantic Custom Auxiliary Data Plugin
        # TODO Separate Window

        # Enable Channels to Plot Plugin (needs to be after parent class)
        self.plugin_active_timeseries_variables = True


    def setup(self, cfg):
        self.logger.debug('Setup')
        if self.alive:
            self.logger.warning('Closing port before updating connection')
            self.close()
        # Check missing fields
        for f in self.REQUIRED_CFG_FIELDS:
            if f not in cfg.keys():
                raise ValueError(f'Missing field %s' % f)
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
        self._log_prod = ProdLogger(logger_cfg, self._parser.cal)
        self.log_raw_enabled = True
        self.log_prod_enabled = cfg['log_products']
        # Update Core Variables Plot
        self._plot.clear()  # Remove all items (past frame headers)
        self._plot_curves = {}
        min_lambda, max_lambda = None, None
        for i, (head, cal) in enumerate(self._parser.cal.items()):
            if cal.core_variables:
                wl = [float(cal.id[i]) for i in cal.core_variables]
                self.wavelengths[head] = wl
                min_lambda = min(min_lambda, min(wl)) if min_lambda is not None else min(wl)
                max_lambda = max(max_lambda, max(wl)) if max_lambda is not None else max(wl)
                self._plot_curves[head] = pg.PlotCurveItem(
                    pen=pg.mkPen(color=COLOR_SET[i % len(COLOR_SET)], width=2),
                    name=head
                )
                self._plot.addItem(self._plot_curves[head])
        # TODO if no core variables do not display core_variable figure
        min_lambda = 0 if min_lambda is None else min_lambda
        max_lambda = 1 if max_lambda is None else max_lambda
        self._plot.setXRange(min_lambda, max_lambda)
        self._plot.setLimits(minXRange=min_lambda, maxXRange=max_lambda)
        # Update Active Timeseries Variables
        self.plugin_active_timeseries_variables_names = []
        self.active_timeseries_variables = []
        for head, cal in self._parser.cal.items():
            self.plugin_active_timeseries_variables_names += [f'{head}_{k}' for k in cal.key if k not in self.KEYS_TO_IGNORE]
            # Append middle core variable to timeseries
            if cal.core_variables:
                idx = cal.core_variables[int(len(cal.core_variables)/2)]
                self.plugin_active_timeseries_variables_selected.append(f'{head}_{cal.key[idx]}')
                self.active_timeseries_variables.append((head, cal.core_groupname, idx))
        # Update User Interface
        self.signal.status_update.emit()

    def data_received(self, data: bytearray, timestamp: float):
        self._buffer.extend(data)
        packet = True
        while packet:
            packet, frame_header, self._buffer, unknown_bytes = self._parser.find_frame(self._buffer)
            if unknown_bytes:
                # Log bytes in raw files
                if self.log_raw_enabled and self._log_active:
                    self._log_raw.write(unknown_bytes)
            if packet:
                self.handle_packet(PacketMaker(packet, frame_header), timestamp)

    def parse(self, packet: PacketMaker):
        try:
            data, valid_frame = self._parser.parse_frame(packet.frame, packet.frame_header, flag_get_auxiliary_variables=True)
        except pySat.ParserError as e:
            self.signal.packet_corrupted.emit()
            self.logger.warning(e)
            self.logger.debug(packet)
        if not valid_frame:
            self.signal.packet_corrupted.emit()
        return PacketMaker(data, packet.frame_header)

    def handle_data(self, data: PacketMaker, timestamp: float):
        # TODO Update auxiliaries
        # Update Timeseries
        if self.active_timeseries_variables_lock.acquire(timeout=0.125):
            try:
                core_groupname = self._parser.cal[data.frame_header].core_groupname
                ts_data = []
                for frame_header, key, idx in self.active_timeseries_variables:
                    if frame_header == data.frame_header:
                        ts_data.append(data.frame[key][idx] if key == core_groupname else data.frame[key])
                    else:
                        ts_data.append(float('nan'))
                self.signal.new_data.emit(ts_data, timestamp)
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update timeseries plot')
        # Update Core Variable Plot
        if self._parser.cal[data.frame_header].core_variables:
            self._plot_curves[data.frame_header].setData(
                self.wavelengths[data.frame_header],
                data.frame[self._parser.cal[data.frame_header].core_groupname]
            )
        # Log Calibrated Data
        if self.log_prod_enabled and self._log_active:
            self._log_prod.write(data, timestamp)
            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()

    def udpate_active_timeseries_variables(self, name:str, state: bool):
        if not ((state and name not in self.plugin_active_timeseries_variables_selected) or
                (not state and name in self.plugin_active_timeseries_variables_selected)):
            return
        frame_header, key, idx = self.active_timeseries_unpack_variable_name(name)
        if self.active_timeseries_variables_lock.acquire(timeout=0.25):
            try:
                if state:
                    self.active_timeseries_variables.append((frame_header, key, idx))
                    self.plugin_active_timeseries_variables_selected.append(name)
                else:
                    del self.active_timeseries_variables[self.active_timeseries_variables.index((frame_header, key, idx))]
                    del self.plugin_active_timeseries_variables_selected[self.plugin_active_timeseries_variables_selected.index(name)]
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update active timeseries variables')

    def active_timeseries_unpack_variable_name(self, name):
        frame_header, key, idx = *name.split('_', 1), 0
        if self._parser.cal[frame_header].core_variables and \
                key.startswith(self._parser.cal[frame_header].core_groupname):
            key, wl = key.split('_')
            idx = self.wavelengths[frame_header].index(float(wl))
        return frame_header, key, idx


class ProdLogger:
    """
    Log Satlantic frames calibrated, with each frame type (frame_header) in a distinct file
    Similar format as Satlantic SatCon output
    :return:
    """
    def __init__(self, log_cfg, cal):
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
            for k, t in zip(v.key, v.data_type):
                if v.core_variables and k.startswith(v.core_groupname):
                    if first_flag:
                        first_flag = False
                        keys.append(v.core_groupname)
                        core.append(True)
                        precision.append('%s')
                elif k not in Satlantic.KEYS_TO_IGNORE:
                    keys.append(k)
                    core.append(False)
                    if t in ['AI', 'BU', 'BS']:
                        precision.append('%d')
                    elif t in ['AF', 'AF16', 'BD', 'BF']:
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
    def FILE_EXT(self) -> str:
        return Log.FILE_EXT

    def update_cfg(self, cfg: dict):
        for l in self._log.values():
            l.update_cfg(cfg)

    def write(self, packet: PacketMaker, timestamp: float):
        data = []
        for k, c in zip(self._frame_keys[packet.frame_header], self._frame_core_var[packet.frame_header]):
            if c:
                data.append(np.array2string(packet.frame[k], separator=', ', max_line_width=np.inf)[1:-1])
            else:
                data.append(packet.frame[k])
        # values = packet.frame.values()  # Assume dictionary keep order which isn't the case with older python version
        self._log[packet.frame_header].write(data, timestamp)

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

    def write(self, packet: PacketMaker, timestamp: float):
        super().write(packet.frame, timestamp)
