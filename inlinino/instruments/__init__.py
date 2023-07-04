import os
import platform
import socket
from threading import Thread
from time import time

import serial
import usb.core
import usb.backend.libusb1
import hid

from inlinino.log import Log, LogText
from inlinino import PATH_TO_RESOURCES
import logging


class Instrument:
    '''
    Generic Interface for Serial Instruments
    '''

    REQUIRED_CFG_FIELDS = ['model', 'serial_number', 'module', 'separator', 'terminator',
                           'log_path', 'log_raw', 'log_products',
                           'variable_columns', 'variable_types',
                           'variable_names', 'variable_units', 'variable_precision']
    DATA_TIMEOUT = 60  # seconds

    def __init__(self, uuid, cfg, signal=None, setup=True):
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
        self.model = ''
        self.serial_number = ''
        self.variable_names = None
        self.variable_units = None
        self.variable_displayed = None
        # widgets
        self.spectrum_plot_enabled = False
        self.widget_aux_data_enabled = False
        self.widget_flow_control_enabled = False
        self.widget_hypernav_cal_enabled = False
        self.widget_metadata_enabled = False
        self.widget_pump_control_enabled = False
        self.widget_select_channel_enabled = False
        self.widgets_to_load = []  # To load widgets disabled on setup

        # Load cfg
        self.uuid = uuid
        if setup:
            self.setup(cfg)

    @property
    def name(self) -> str:
        return self.model + ' ' + self.serial_number

    @property
    def short_name(self) -> str:
        name = self.model + ' ' + self.serial_number
        return name if len(name) < 14 else self.model[0:5].strip() + ' ... ' + self.serial_number[0:5].strip()

    @property
    def interface_name(self) -> str:
        return self._interface.name

    @property
    def interface_signal(self):
        return self._interface.signal

    @property
    def bare_log_prefix(self) -> str:
        return self.model + self.serial_number

    @property
    def secondary_dock_widget_enabled(self) -> bool:
        return self.widget_metadata_enabled or \
            self.widget_flow_control_enabled or \
            self.widget_pump_control_enabled or \
            self.widget_hypernav_cal_enabled

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
        self.setup_interface(cfg)
        self._terminator = cfg['terminator']
        # Logger
        self.model = cfg['model']
        self.serial_number = cfg['serial_number']
        log_cfg = {'path': cfg['log_path'], 'filename_prefix': self.bare_log_prefix}
        for k in ['length', 'variable_names', 'variable_units', 'variable_precision']:
            if k in cfg.keys():
                log_cfg[k] = cfg[k]
        if not self._log_raw:
            self.logger.debug('Init loggers')
            self._log_raw = raw_logger(log_cfg, self.signal.status_update)
            self._log_prod = Log(log_cfg, self.signal.status_update)
        else:
            self.log_update_cfg(log_cfg)
        self._log_active = False  # Needed in case thread doesn't join during self.close()
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
        self.variable_names = cfg['variable_names']
        self.variable_units = cfg['variable_units']
        self.signal.status_update.emit()  # Doesn't run on initial setup because signals are not connected

    def setup_interface(self, cfg):
        if 'interface' in cfg.keys():
            if cfg['interface'] == 'serial':
                self._interface = SerialInterface()
            elif cfg['interface'] == 'socket':
                self._interface = SocketInterface()
            elif cfg['interface'] == 'usb-hid':
                self._interface = USBHIDInterface()
            elif cfg['interface'] == 'usb':
                self._interface = USBInterface()
            else:
                raise ValueError(f'Invalid communication interface {cfg["interface"]}')

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
                timeout = self._interface.timeout if self._interface.timeout is not None else 1
                self._thread.join(timeout)
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
                            if self.signal.alarm is not None:
                                self.signal.alarm.emit(False)
                    except Exception as e:
                        self.logger.warning(e)
                        # raise e
                else:
                    if data_received is not None and \
                            timestamp - data_received > self.DATA_TIMEOUT and data_timeout_flag is False:
                        self.logger.error(f'No data received during the past {timestamp - data_received:.2f} seconds')
                        data_timeout_flag = True
                        if self.signal.alarm is not None:
                            self.signal.alarm.emit(True)
            except InterfaceException as e:
                # probably some I/O problem such as disconnected USB serial
                # adapters -> exit
                self.logger.error(e)
                if self.signal.alarm is not None:
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
        self.signal.new_ts_data.emit(data, timestamp)
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

    @property
    def log_active(self):
        return self._log_active

    @property
    def log_path(self):
        return self._log_raw.path

    @property
    def log_filename(self):
        if self.log_raw_enabled or not self.log_prod_enabled:
            return self._log_raw.filename
        else:
            return self._log_prod.filename

    def log_get_file_ext(self):
        if self.log_raw_enabled or not self.log_prod_enabled:
            return self._log_raw.FILE_EXT
        else:
            return self._log_prod.FILE_EXT

    def log_update_cfg(self, log_cfg):
        self.logger.debug('Update loggers configuration')
        self._log_raw.update_cfg(log_cfg)
        self._log_prod.update_cfg(log_cfg)

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


class InterfaceException(IOError):
    pass


class Interface:
    @property
    def is_open(self) -> bool:
        raise NotImplementedError

    @property
    def timeout(self) -> int:
        raise NotImplementedError

    @timeout.setter
    def timeout(self, value):
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError

    def open(self, **kwargs):
        pass

    def init(self):
        # Typically, run once after connection is opened
        pass

    def stop(self):
        # Typically, run once before closing connection
        pass

    def close(self):
        pass

    def read(self, size=None):
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

    @timeout.setter
    def timeout(self, value: int):
        self._serial.timeout = value

    @property
    def name(self) -> str:
        if self.is_open:
            return f'com:{self._serial.port}'
        else:
            return f'com'

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

    def read(self, size=None):
        try:
            return self._serial.read(self._serial.in_waiting or 1 if size is None else size)
        except serial.SerialException as e:
            raise InterfaceException(e)

    def read_until(self, expected=b'\n', size=None):
        return self._serial.read_until(expected=expected, size=size)

    def write(self, data):
        self._serial.write(data)


class SocketInterface(Interface):
    def __init__(self):
        self._socket = None
        self._is_open = False

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def timeout(self) -> int:
        return self._socket.gettimeout()

    @property
    def name(self) -> str:
        if self.is_open:
            ip, port = self._socket.getsockname()
            return f'socket:{port}'
        else:
            return f'socket'

    def open(self, ip, port, timeout=1):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((ip, port))
        # self._socket.settimeout(timeout)
        self._is_open = True

    def close(self):
        self._is_open = False
        if self._socket is not None:
            self._socket.close()

    def read(self, size=65536):
        return self._socket.recv(size)
        # return self._socket.recvfrom(socket.CMSG_SPACE(200))[0]  # socket.CMSG_SPACE is not supported by Windows

    def write(self, data):
        self._socket.send(data)


class USBInterface(Interface):
    """
    Based on libusb interfaced through pyusb compatible with Linux, Darwin, and Windows
    Requirements: pyusb=1.0.2
    Warning: dll for windows might only be compatible with ontrak ADU devices
    """

    def __init__(self):
        self._device: usb.core.Device = None
        self._timeout = 200  # ms
        self._linux_kernel_drive_was_active = False
        self.read_endpoint, self.write_endpoint = 0x81, 0x01

    @property
    def is_open(self) -> bool:
        return self._device is not None

    @property
    def timeout(self) -> int:
        return self._timeout / 1000  # in seconds

    @timeout.setter
    def timeout(self, value: float):
        self._timeout = int(value * 1000)

    @property
    def name(self) -> str:
        if self.is_open:
            return f'usb:{self._device.serial_number}'
        else:
            return f'usb'

    def open(self, vendor_id, product_id):
        try:
            # Load backend (Windows dll)
            backend = None
            if platform.system() == 'Windows':
                arch = platform.architecture()[0]
                mapa = {'32bit': 'x86', '64bit': 'x64'}
                if arch not in mapa.keys():
                    raise ValueError(f'Architecture {arch} not supported.')
                backend = usb.backend.libusb1.get_backend(
                    find_library=lambda x: os.path.join(PATH_TO_RESOURCES, 'libusb', mapa[arch], 'crap.dll'))
                print(backend)
                print(os.path.join(PATH_TO_RESOURCES, 'libusb', mapa[arch], 'libusb-1.0.dll'))
            # Find device
            self._device = usb.core.find(backend=backend, idVendor=vendor_id, idProduct=product_id)
            # Special case for linux
            if platform.system() in 'Linux':
                if self._device.is_kernel_driver_active(0) is True:
                    # tell the kernel to detach
                    self._device.detach_kernel_driver(0)
                    self._linux_kernel_drive_was_active = True
            if self.is_open:
                self._device.reset()
                # Set active configuration
                self._device.set_configuration()
                # Claim interface 0
                usb.util.claim_interface(self._device, 0)
        except (IOError, ValueError) as e:
            raise InterfaceException(f'Try with another USB interface.\n{repr(e)}')
        if not self.is_open:
            raise InterfaceException('USB device not found. Please ensure it is connected.')

    def close(self):
        if self.is_open:
            usb.util.release_interface(self._device, 0)
            if self._linux_kernel_drive_was_active:
                self._device.attach_kernel_driver(0)
            self._device = None

    def read(self, size=1):
        # size is converted from bytes to bits
        return self._device.read(self.read_endpoint, size * 8, timeout=self._timeout)

    def write(self, data):
        return self._device.write(self.write_endpoint, data)


class USBHIDInterface(Interface):
    """
    Based HID API compatible with Linux, Darwin, and Windows
    Does not require additional dll for windows
    Warning: bug have been encountered on windows
    """

    def __init__(self):
        self._device = hid.device()
        self._is_open = False
        self._timeout = 200  # ms

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def timeout(self) -> int:
        return self._timeout / 1000  # in seconds

    @timeout.setter
    def timeout(self, value: float):
        self._timeout = int(value*1000)

    @property
    def name(self) -> str:
        if self.is_open:
            return f'usb-hid:{self._device.get_serial_number_string()}'
        else:
            return f'usb-hid'

    def open(self, vendor_id, product_id):
        try:
            self._device = hid.device()
            self._device.open(vendor_id, product_id)
            self._is_open = True
        except (IOError, RuntimeError, OSError) as e:
            self._is_open = False
            raise InterfaceException(e)

    def close(self):
        if self.is_open:
            try:
                self._device.close()
            finally:
                self._is_open = False

    def read(self, size=1):
        return self._device.read(size, self._timeout)

    def write(self, data):
        return self._device.write(data)


def get_spy_interface(interface: Interface, echo=True):
    class Spy(interface):
        def __init__(self, signal, max_buffer=2 ** 20):
            super().__init__()
            self.signal = signal
            self.spy_enabled = True

        def read(self, *args, **kwargs):
            buffer = super().read(*args, **kwargs)
            # self.read_queue += buffer
            # if len(self.read_queue) > self.max_buffer:
            #     self.read_queue = self.read_queue[-self.max_buffer:]
            if self.spy_enabled and len(buffer) > 0:
                self.signal.read.emit(buffer)
            return buffer

        def write(self, data: bytes):
            # self.write_queue += data
            # if len(self.write_queue) > self.max_buffer:
            #     self.write_queue = self.write_queue[-self.max_buffer:]
            if self.spy_enabled and echo:
                self.signal.write.emit(data)
            return super().write(data)

    return Spy


def _generate_crc16_table():
    """Generate a crc16 lookup table.

    .. note:: This will only be generated once
    """
    result = []
    for byte in range(256):
        crc = 0x0000
        for _ in range(8):
            if (byte ^ crc) & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
            byte >>= 1
        result.append(crc)
    return result


class ModbusProtocol:
    CRC16_TABLE = _generate_crc16_table()

    def __init__(self, address: bytearray = b'\x01'):
        self.address = address

    def request(self, register: int, quantity_of_registers: int = 1, function: bytearray = b'\x03') ->bytearray:
        frame = self.address + function + register.to_bytes(2, 'big') + quantity_of_registers.to_bytes(2, 'big')
        frame += self.compute_crc(frame).to_bytes(2, 'big')
        return frame

    def handle_response(self, response: bytearray) -> bytearray:
        if self.compute_crc(response[:-2]) != int.from_bytes(response[-2:], 'big'):
            raise ValueError('Invalid CRC.')
        address = response[0:1]  # Keep as bytearray
        if address != self.address:
            raise ValueError('Invalid address.')
        code = response[1]
        if code == 0x83:  # Error Code
            exception_code = response[2]
            if exception_code == 0x01:
                raise ValueError('Function code not supported.')
            elif exception_code == 0x02:
                raise ValueError('Invalid starting address or quantity of registers.')
            elif exception_code == 0x03:
                raise ValueError('Invalid quantity of registers.')
            elif exception_code == 0x04:
                raise ValueError('Unable to read multiple registers.')
            else:
                raise ValueError('Error occurred.')
        if code != 0x03:  # Function Read Holding Register
            raise NotImplementedError(f'Function code {hex(code)} not implemented.')
        byte_count = response[2]
        return response[3:3 + byte_count]

    @staticmethod
    def compute_crc(data: bytearray) -> int:  # pylint: disable=invalid-name
        """Compute a crc16 on the passed in string.
        source: pymodbus

        For modbus, this is only used on the binary serial protocols (in this
        case RTU).

        The difference between modbus's crc16 and a normal crc16
        is that modbus starts the crc value out at 0xffff.

        :param data: The data to create a crc16 of
        :returns: The calculated CRC
        """
        crc = 0xFFFF
        for data_byte in data:
            idx = ModbusProtocol.CRC16_TABLE[(crc ^ int(data_byte)) & 0xFF]
            crc = ((crc >> 8) & 0xFF) ^ idx
        swapped = ((crc << 8) & 0xFF00) | ((crc >> 8) & 0x00FF)
        return swapped
