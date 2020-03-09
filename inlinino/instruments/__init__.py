import serial
from threading import Thread
from time import time
from log import Log, LogText


class Instrument:
    '''
    Generic Interface for Serial Instruments
    '''

    ENCODING = 'utf-8'

    def __init__(self, name, cfg=None, ui=None):
        self.name = name

        # Set Default Config (TODO update to configparser)
        if 'baudrate' not in cfg.keys():
            cfg['baudrate'] = 19200
        if 'bytesize' not in cfg.keys():
            cfg['bytesize'] = 8
        if 'parity' not in cfg.keys():
            cfg['parity'] = 'N'
        if 'stopbits' not in cfg.keys():
            cfg['stopbits'] = 1
        if 'timeout' not in cfg.keys():
            cfg['timeout'] = 2
        if 'separator' not in cfg.keys():
            cfg['separator'] = '\t'
        if 'terminator' not in cfg.keys():
            cfg['terminator'] = '\r\n'
        if 'variable_columns' not in cfg.keys():
            cfg['variable_columns'] = []
        if 'variable_types' not in cfg.keys():
            cfg['variable_types'] = []
        if 'variable_names' not in cfg.keys():
            cfg['variable_names'] = []
        if 'variable_columns' not in cfg.keys():
            cfg['variable_units'] = []
        if 'variable_displayed' not in cfg.keys():
            if 'variable_names' in cfg.keys():
                cfg['variable_displayed'] = cfg['variable_names']
            else:
                cfg['variable_displayed'] = []
        if 'filename_prefix' not in cfg.keys():
            cfg['filename_prefix'] = self.name
        if 'log_raw' not in cfg.keys():
            cfg['log_raw'] = True
        if 'log_products' not in cfg.keys():
            cfg['log_products'] = True

        # Check configuration
        if len(cfg['variable_columns']) != len(cfg['variable_types']):
            raise ValueError("Variable columns and types must be the same length in the configuration.")
        if 'variable_precision' in cfg.keys():
            if cfg['variable_precision']:
                if len(cfg['variable_precision']) != len(cfg['variable_columns']):
                    raise ValueError("Variable precision and columns must be the same length in the configuration.")

        # Serial
        self._serial = serial.Serial()
        self._serial.baudrate = cfg['baudrate']
        self._serial.bytesize = cfg['bytesize']
        self._serial.parity = cfg['parity']
        self._serial.stopbits = cfg['stopbits']
        self._serial.timeout = cfg['timeout']
        self._terminator = cfg['terminator'].encode(self.ENCODING)
        self._buffer = bytearray()
        self._max_buffer_length = 16384

        # Thread
        self._thread = None
        self.alive = False  # Might be replaced by Thread.is_alive()

        # Logger
        self._log_raw = LogText(cfg)
        self._log_prod = Log(cfg)
        self._log_active = False
        self.log_raw_enable = cfg['log_raw']
        self.log_prod_enable = cfg['log_products']

        # Simple parser
        self.separator = cfg['separator'].encode(self.ENCODING)
        self.variable_columns = cfg['variable_columns']
        self.variable_types = cfg['variable_types']

        # User Interface
        self.ui = ui
        self.variable_names = cfg['variable_names']
        self.variable_units = cfg['variable_units']
        self.variable_displayed = [cfg['variable_names'].index(foo) for foo in cfg['variable_displayed']]
        self.packet_received = 0
        self.packet_corrupted = 0
        self.packet_logged = 0
        self.require_port = True

    def open(self, port=None):
        if port is None:
            raise ValueError('The instrument requires a port.')
        if not self.alive:
            # Reset Packet Counts
            self.packet_received = 0
            self.packet_corrupted = 0
            self.packet_logged = 0
            # Open serial connection
            self._serial.port = port
            self._serial.open()
            self.alive = True
            # Start reading/writing thread
            self._thread = Thread(name=self.name, target=self.run)
            self._thread.daemon = True
            self._thread.start()

    def close(self, wait_thread_join=True):
        if self.alive:
            self.alive = False
            if hasattr(self._serial, 'cancel_read'):
                self._serial.cancel_read()
            if wait_thread_join:
                self._thread.join(2)
                if self._thread.is_alive():
                    print('Thread of instrument %s did not join.' % self.name)
            self.log_stop()
            self._serial.close()

    def run(self):
        if self._serial.is_open:
            # Empty buffers
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            if self._serial.in_waiting > 0:
                self._serial.read(self._serial.in_waiting)
        while self.alive and self._serial.is_open:
            try:
                # read all that is there or wait for one byte (blocking)
                data = self._serial.read(self._serial.in_waiting or 1)
                if data:
                    try:
                        self.data_received(data)
                        if len(self._buffer) > self._max_buffer_length:
                            print('Buffer exceeded maximum length. Buffer emptied to prevent overflow')
                            self._buffer = bytearray()
                    except Exception as e:
                        print(self.name)
                        print(e)
            except serial.SerialException as e:
                # probably some I/O problem such as disconnected USB serial
                # adapters -> exit
                print(self.name)
                print(e)
                break
        self.close(wait_thread_join=False)

    def data_received(self, data):
        self._buffer.extend(data)
        while self._terminator in self._buffer:
            packet, self._buffer = self._buffer.split(self._terminator, 1)
            try:
                self.handle_packet(packet)
            except IndexError:
                self.packet_corrupted += 1
                print(self.name + 'Incomplete packet or Incorrect variable column requested.')
                print(packet)
                self.ui.InstrumentUpdate(self.name)
            except ValueError:
                self.packet_corrupted += 1
                print(self.name + 'Instrument or parser configuration incorrect.')
                print(packet)
                self.ui.InstrumentUpdate(self.name)
            except Exception as e:
                self.packet_corrupted += 1
                print(self.name)
                print(e)
                print(packet)
                self.ui.InstrumentUpdate(self.name)

    def handle_packet(self, packet):
        timestamp = time()
        self.packet_received += 1
        self.write_to_serial()
        if self.log_raw_enable and self._log_active:
            self._log_raw.write(packet, timestamp)
            self.packet_logged += 1
        data = self.parse(packet)
        if self.ui:
            self.ui.InstrumentUpdate(self.name, data, timestamp)
        if self.log_prod_enable and self._log_active:
            self._log_prod.write(data, timestamp)
            if not self.log_raw_enable:
                self.packet_logged += 1

    def log_start(self):
        self._log_active = True

    def log_stop(self):
        self._log_active = False
        self._log_raw.close()
        self._log_prod.close()

    def log_status(self):
        return self._log_active

    def log_set_filename_prefix(self, prefix):
        if prefix:
            self._log_raw.filename_prefix = prefix + '_' + self.name
            self._log_prod.filename_prefix = prefix + '_' + self.name
        else:
            self._log_raw.filename_prefix = self.name
            self._log_prod.filename_prefix = self.name

    def log_get_path(self):
        return self._log_raw.path

    def log_set_path(self, path):
        self._log_raw.path = path
        self._log_prod.path = path

    def write_to_serial(self):
        # if self._serial.is_open:
        #     self._serial.write(b'Hello' + self._terminator) # Pay attention to encoding
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
