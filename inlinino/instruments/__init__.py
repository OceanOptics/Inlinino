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

    def __init__(self, cfg_id, signal=None):
        self.__logger = logging.getLogger(self.__class__.__name__)

        # Serial
        self._serial = serial.Serial()
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

        # Load cfg
        self.cfg_id = cfg_id
        self.setup(CFG.instruments[self.cfg_id])

    def setup(self, cfg, raw_logger=LogText):
        self.__logger.debug('Setup')
        if self.alive:
            self.__logger.warning('Closing port before updating connection')
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
        # Serial
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
            self.__logger.debug('Init loggers')
            self._log_raw = raw_logger(log_cfg, self.signal.status_update)
            self._log_prod = Log(log_cfg, self.signal.status_update)
        else:
            self.__logger.debug('Update loggers configuration')
            self._log_raw.update_cfg(log_cfg)
            self._log_prod.update_cfg(log_cfg)
        self._log_active = False
        self.log_raw_enabled = cfg['log_raw']
        self.log_prod_enabled = cfg['log_products']
        # Simple parser
        if 'separator' in cfg.keys():
            self.separator = cfg['separator']
            self.variable_columns = cfg['variable_columns']
            self.variable_types = cfg['variable_types']
        # User Interface
        # self.manufacturer = cfg['manufacturer']
        # self.model = cfg['model']
        # self.serial_number = cfg['serial_number']
        self.name = cfg['model'] + ' ' + cfg['serial_number']
        self.variable_names = cfg['variable_names']
        self.variable_units = cfg['variable_units']
        self.signal.status_update.emit()

    def open(self, port=None, baudrate=19200, bytesize=8, parity='N', stopbits=1, timeout=2):
        if port is None:
            raise ValueError('The instrument requires a port.')
        if not self.alive:
            # Open serial connection
            self._serial.port = port
            self._serial.baudrate = baudrate
            self._serial.bytesize = bytesize
            self._serial.parity = parity
            self._serial.stopbits = stopbits
            self._serial.timeout = timeout
            self._serial.open()
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
            if hasattr(self._serial, 'cancel_read'):
                self._serial.cancel_read()
            if wait_thread_join:
                self._thread.join(self._serial.timeout)
                if self._thread.is_alive():
                    self.__logger.warning('Thread did not join.')
            self.log_stop()
            self._serial.close()

    def run(self):
        if self._serial.is_open:
            # Empty buffers
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            if self._serial.in_waiting > 0:
                self._serial.read(self._serial.in_waiting)
            # Send init frame to instrument
            self.init_serial()
        while self.alive and self._serial.is_open:
            try:
                # read all that is there or wait for one byte (blocking)
                data = self._serial.read(self._serial.in_waiting or 1)
                if data:
                    try:
                        self.data_received(data)
                        if len(self._buffer) > self._max_buffer_length:
                            self.__logger.warning('Buffer exceeded maximum length. Buffer emptied to prevent overflow')
                            self._buffer = bytearray()
                    except Exception as e:
                        self.__logger.warning(e)
            except serial.SerialException as e:
                # probably some I/O problem such as disconnected USB serial
                # adapters -> exit
                self.__logger.error(e)
                break
        self.close(wait_thread_join=False)

    def data_received(self, data):
        self._buffer.extend(data)
        while self._terminator in self._buffer:
            packet, self._buffer = self._buffer.split(self._terminator, 1)
            try:
                self.handle_packet(packet)
            except IndexError:
                self.signal.packet_corrupted.emit()
                self.__logger.warning('Incomplete packet or Incorrect variable column requested.')
                self.__logger.debug(packet)
                # if __debug__:
                #     raise
            except ValueError:
                self.signal.packet_corrupted.emit()
                self.__logger.warning('Instrument or parser configuration incorrect.')
                self.__logger.debug(packet)
                # if __debug__:
                #     raise
            except Exception as e:
                self.signal.packet_corrupted.emit()
                self.__logger.warning(e)
                self.__logger.debug(packet)
                # if __debug__:
                #     raise e

    def handle_packet(self, packet):
        timestamp = time()
        self.signal.packet_received.emit()
        self.write_to_serial()
        if self.log_raw_enabled and self._log_active:
            self._log_raw.write(packet, timestamp)
            self.signal.packet_logged.emit()
        data = self.parse(packet)
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

    def init_serial(self):
        pass

    def write_to_serial(self):
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
