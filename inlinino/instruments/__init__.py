import socket
import serial
from threading import Thread
from time import time
from inlinino.log import Log, LogText
from inlinino import CFG
import logging


class Instrument:
    '''
    Generic Interface for Serial Instruments
    '''

    REQUIRED_CFG_FIELDS = ['model', 'serial_number', 'module', 'separator', 'terminator',
                           'log_path', 'log_raw', 'log_products',
                           'variable_columns', 'variable_types', 'variable_names', 'variable_units', 'variable_precision']
    DATA_TIMEOUT = 60  # seconds

    def __init__(self, cfg_id, signal=None):
        self.logger = logging.getLogger(self.__class__.__name__)

        # Communication Interface
        self._interface = SerialInterface()
        self._terminator = None
        self._buffer = bytearray()
        self._max_buffer_length = 16384

        # Thread
        self._thread = None
        self.alive = False  # Might be replaced by Thread.is_alive()

        # Logger
        self._log_raw = None
        self._log_prod = None
        self._log_active = False
        self.log_raw_enabled = False
        self.log_prod_enabled = False

        # Simple parser
        self.separator = None
        self.variable_columns = None
        self.variable_types = None

        # User Interface
        self.signal = signal
        self.name = ''
        self.variable_names = None
        self.variable_units = None
        self.variable_displayed = None
        self.plugin_aux_data = False
        self.plugin_active_timeseries_variables = False

        # Load cfg
        self.cfg_id = cfg_id
        self.setup(CFG.instruments[self.cfg_id].copy())

    def setup(self, cfg, raw_logger=LogText):
        self.logger.debug('Setup')
        if self.alive:
            self.logger.warning('Closing port before updating connection')
            self.close()
        # Check missing fields
        for f in self.REQUIRED_CFG_FIELDS:
            if f not in cfg.keys():
                raise ValueError('Missing field %s' % f)
        # Check configuration
        variable_keys = [v for v in cfg.keys() if 'variable_' in v]
        if variable_keys:
            # Check length
            n = len(cfg['variable_names'])
            for k in variable_keys:
                if n != len(cfg[k]):
                    raise ValueError('%s invalid length' % k)
        # Communication Interface (for retro-compatibility: default interface is serial)
        if 'interface' in cfg.keys():
            if cfg['interface'] == 'serial':
                self._interface = SerialInterface()
            elif cfg['interface'] == 'socket':
                self._interface = SocketInterface()
            else:
                raise ValueError(f'Invalid communication interface {cfg["interface"]}')
        self._terminator = cfg['terminator']
        # Logger
        log_cfg = {'path': cfg['log_path']}
        if 'log_prefix' in cfg.keys():
            log_cfg['filename_prefix'] = cfg['log_prefix'] + cfg['model'] + cfg['serial_number']
        else:
            log_cfg['filename_prefix'] = cfg['model'] + cfg['serial_number']
        for k in ['length', 'variable_names', 'variable_units', 'variable_precision']:
            if k in cfg.keys():
                log_cfg[k] = cfg[k]
        if not self._log_raw:
            self.logger.debug('Init loggers')
            self._log_raw = raw_logger(log_cfg, self.signal.status_update)
            self._log_prod = Log(log_cfg, self.signal.status_update)
        else:
            self.logger.debug('Update loggers configuration')
            self._log_raw.update_cfg(log_cfg)
            self._log_prod.update_cfg(log_cfg)
        self._log_active = False
        self.log_raw_enabled = cfg['log_raw']
        self.log_prod_enabled = cfg['log_products']
        # Simple parser
        if 'separator' in cfg.keys():
            self.separator = cfg['separator']
        if 'variable_columns' in cfg.keys():
            self.variable_columns = cfg['variable_columns']
        if 'variable_types' in cfg.keys():
            self.variable_types = cfg['variable_types']
        # User Interface
        # self.manufacturer = cfg['manufacturer']
        # self.model = cfg['model']
        # self.serial_number = cfg['serial_number']
        self.name = cfg['model'] + ' ' + cfg['serial_number']
        self.variable_names = cfg['variable_names']
        self.variable_units = cfg['variable_units']
        self.signal.status_update.emit()

    def open(self, **kwargs):
        if not self.alive:
            # Open serial connection
            self._interface.open(**kwargs)
            self.alive = True
            # Start reading/writing thread
            self._thread = Thread(name=self.name, target=self.run)
            self._thread.daemon = True
            self._thread.start()
            # Signal to UI
            self.signal.status_update.emit()

    def close(self, wait_thread_join=True):
        if self.alive:
            self.alive = False
            self.signal.status_update.emit()
            self._interface.stop()
            if wait_thread_join:
                self._thread.join(self._interface.timeout)
                if self._thread.is_alive():
                    self.logger.warning('Thread did not join.')
            self.log_stop()
            self._interface.close()
            self._buffer = bytearray()

    def run(self):
        if self._interface.is_open:
            # Initialize interface (typically empty buffers)
            self._interface.init()
            # Send init frame to instrument
            self.init_interface()
            # Set data timeout flag
            data_timeout_flag = False
            data_received = None
        while self.alive and self._interface.is_open:
            try:
                # read all that is there or wait for one byte (blocking)
                data = self._interface.read()
                timestamp = time()
                if data:
                    try:
                        self.data_received(data, timestamp)
                        if len(self._buffer) > self._max_buffer_length:
                            self.logger.warning('Buffer exceeded maximum length. Buffer emptied to prevent overflow')
                            self._buffer = bytearray()
                        data_received = timestamp
                        if data_timeout_flag:
                            data_timeout_flag = False
                            self.signal.alarm.emit(False)
                    except Exception as e:
                        self.logger.warning(e)
                        # raise e
                else:
                    if data_received is not None and \
                            timestamp - data_received > self.DATA_TIMEOUT and data_timeout_flag is False:
                        self.logger.error(f'No data received during the past {timestamp - data_received:.2f} seconds')
                        data_timeout_flag = True
                        self.signal.alarm.emit(True)
            except InterfaceException as e:
                # probably some I/O problem such as disconnected USB serial
                # adapters -> exit
                self.logger.error(e)
                self.signal.alarm.emit(True)
                break
        self.close(wait_thread_join=False)

    def data_received(self, data, timestamp):
        self._buffer.extend(data)
        while self._terminator in self._buffer:
            packet, self._buffer = self._buffer.split(self._terminator, 1)
            try:
                self.handle_packet(packet, timestamp)
            except IndexError:
                self.signal.packet_corrupted.emit()
                self.logger.warning('Incomplete packet or Incorrect variable column requested.')
                self.logger.debug(packet)
                # raise
            except ValueError:
                self.signal.packet_corrupted.emit()
                self.logger.warning('Instrument or parser configuration incorrect.')
                self.logger.debug(packet)
                # raise
            except Exception as e:
                self.signal.packet_corrupted.emit()
                self.logger.warning(e)
                self.logger.debug(packet)
                # raise e

    def handle_packet(self, packet, timestamp):
        self.signal.packet_received.emit()
        self.write_to_interface()
        if self.log_raw_enabled and self._log_active:
            self._log_raw.write(packet, timestamp)
            self.signal.packet_logged.emit()
        data = self.parse(packet)
        if data:
            self.handle_data(data, timestamp)

    def handle_data(self, data, timestamp):
        self.signal.new_data.emit(data, timestamp)
        if self.log_prod_enabled and self._log_active:
            self._log_prod.write(data, timestamp)
            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()

    def log_start(self):
        self._log_active = True
        self.signal.status_update.emit()

    def log_stop(self):
        self._log_active = False
        self.signal.status_update.emit()
        self._log_raw.close()
        self._log_prod.close()

    def log_active(self):
        return self._log_active

    def log_get_path(self):
        return self._log_raw.path

    def log_get_filename(self):
        if self.log_raw_enabled or not self.log_prod_enabled:
            return self._log_raw.filename
        else:
            return self._log_prod.filename

    def init_interface(self):
        pass

    def write_to_interface(self):
        pass

    def parse(self, packet):
        foo = packet.split(self.separator)
        bar = []
        for c, t in zip(self.variable_columns, self.variable_types):
            if t == "int":
                bar.append(int(foo[c]))
            elif t == "float":
                bar.append(float(foo[c]))
            else:
                raise ValueError("Variable type not supported.")
        return bar

    def __str__(self):
        if self.alive:
            if self._log_active:
                return self.name + '[alive][logging]'
            else:
                return self.name + '[alive][log-off]'
        else:
            return self.name + '[off]'


class InterfaceException(Exception):
    pass


class Interface:
    def __init__(self):
        self._is_open = False
        self._timeout = 1

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def timeout(self) -> int:
        return self._timeout

    def open(self, **kwargs):
        pass

    def init(self):
        # typically run once after connection is openned
        pass

    def stop(self):
        # typically run once before closing connection
        pass

    def close(self):
        pass

    def read(self):
        pass

    def write(self, data):
        pass


class SerialInterface(Interface):
    def __init__(self):
        self._serial = serial.Serial()

    @property
    def is_open(self) -> bool:
        return self._serial.is_open

    @property
    def timeout(self) -> int:
        return self._serial.timeout

    def open(self, port=None, baudrate=19200, bytesize=8, parity='N', stopbits=1, timeout=2):
        if port is None:
            raise ValueError('SerialInterface requires a port.')
        # Open serial connection
        try:
            self._serial.port = port
            self._serial.baudrate = baudrate
            self._serial.bytesize = bytesize
            self._serial.parity = parity
            self._serial.stopbits = stopbits
            self._serial.timeout = timeout
            self._serial.open()
        except serial.SerialException as e:
            raise InterfaceException(f'Unable to connect port {port}.\n{e}')

    def init(self):
        # Empty buffers
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()
        if self._serial.in_waiting > 0:
            self._serial.read(self._serial.in_waiting)

    def stop(self):
        if hasattr(self._serial, 'cancel_read'):
            self._serial.cancel_read()

    def close(self):
        self._serial.close()

    def read(self):
        try:
            return self._serial.read(self._serial.in_waiting or 1)
        except serial.SerialException as e:
            raise InterfaceException(e)

    def write(self, data):
        self._serial.write(data)


class SocketInterface(Interface):
    def __init__(self):
        super().__init__()
        self._socket = None

    @property
    def timeout(self) -> int:
        return self._socket.gettimeout()

    def open(self, ip, port, timeout=1):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((ip, port))
        # self._socket.settimeout(timeout)
        self._is_open = True

    def close(self):
        self._is_open = False
        if self._socket is not None:
            self._socket.close()

    def read(self):
        return self._socket.recv(65536)
        # return self._socket.recvfrom(socket.CMSG_SPACE(200))[0]  # socket.CMSG_SPACE is not supported by Windows

    def write(self, data):
        self._socket.send(data)

