from time import time, sleep, strftime
from dataclasses import dataclass, field
from typing import List
from math import isnan
import platform

from inlinino.instruments import Instrument, USBInterface, USBHIDInterface, InterfaceException, Interface
from inlinino.log import LogText

if platform.system() == 'Windows':
    from inlinino.resources.ontrak import aduhid
else:
    aduhid = None


RELAY_OFF = 0
RELAY_ON = 1
RELAY_HOURLY = 2
RELAY_INTERVAL = 3
GALLONS_TO_LITERS = 3.78541


@dataclass
class ADUPacket:
    relay: bool = None
    event_counter_values: List[int] = field(default_factory=list)
    event_counter_timestamps: List[float] = field(default_factory=list)
    analog_values: List[int] = field(default_factory=list)

    def decode(self, *args, **kwargs):
        return self.__repr__()

    def __repr__(self):
        """
        Packet representation for raw data logging
        :return:
        """
        repr = f'{self.relay}' if self.relay is not None else ''
        for t, v in zip(self.event_counter_timestamps, self.event_counter_values):
            repr += f', {t}, {v}' if repr else f'{t}, {v}'
        for v in self.analog_values:
            repr += f', {v}' if repr else f'{v}'
        return repr

    def __bool__(self):
        if self.relay is not None or self.event_counter_values or self.analog_values:
            return True
        return False


class Ontrak(Instrument):
    """
    ontrak Control Systems Data Acquisition Interface
    Supported Model: ADU100
    """

    VENDOR_ID = 0x0a07

    # Specific ADU 100
    ADC_RESOLUTION = 65535
    # UNIPOLAR_GAIN = {
    #     0: {0: 1, 1: 2, 2: 4, 3: 8, 4: 16, 5: 32, 6: 64, 7: 128},
    #     1: {0: 1, 1: 2, 2: 4, 3: 8, 4: 16, 5: 32, 6: 64, 7: 128},
    #     2: {1: 1, 2: 2},
    # }
    UNIPOLAR_MAX_VOLTAGE = {
        0: {0: 2.5, 1: 1.25, 2: 0.625, 3: 0.3125, 4: 0.15625, 5: 0.078125, 6: 0.0390625, 7: 0.01953125},
        1: {0: 2.5, 1: 1.25, 2: 0.625, 3: 0.3125, 4: 0.15625, 5: 0.078125, 6: 0.0390625, 7: 0.01953125},
        2: {1: 10, 2: 5},
    }

    REQUIRED_CFG_FIELDS = ['relay0_enabled', 'relay0_mode',
                           'event_counter_channels_enabled', 'event_counter_k_factors',
                           'analog_channels_enabled', 'analog_channels_gains',
                           'model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_precision']

    def __init__(self, uuid, cfg, signal, *args, **kwargs):
        super().__init__(uuid, cfg, signal, *args, setup=False, **kwargs)
        # Instrument Specific attributes
        # Relay
        self.relay_enabled = True
        # TODO Store four parameters below in configuration file to replicate main interface
        self.relay_mode = 'Switch'
        self.relay_status = RELAY_HOURLY
        self.relay_hourly_start_at = 0   # minutes
        self.relay_on_duration = 10      # minutes
        self.relay_off_duration = 30     # minutes
        self._relay_interval_start = None
        self._relay_hourly_skip_before = 0
        self._relay_cached_position = None
        # Event Counter(s) / Flowmeter(s)
        self.event_counter_channels = [0]
        self.event_counter_k_factors = [1381]
        self._event_counter_past_timestamps = [float('nan')] * len(self.event_counter_channels)
        # Analog Channel(s)
        self.analog_channels = [2]
        self.analog_gains = [2]  # 5V Gain on channel 2 for ADU100
        self._analog_calibration_timestamp = None
        self._analog_calibration_interval = 3600  # seconds
        # Refresh rate
        self.refresh_rate = 2  # Hz
        # Init Auxiliary Data Widget
        self.widget_aux_data_enabled = True
        self.widget_aux_data_variable_names = []
        # Init Flow Control Widget
        self.widget_flow_control_enabled = True
        self.widget_pump_control_enabled = True
        self.widgets_to_load = ['FlowControlWidget', 'PumpControlWidget']
        # Setup
        self.setup(cfg)

    def setup(self, cfg, raw_logger=LogText):
        # Set specific attributes
        if 'model' not in cfg.keys():
            raise ValueError('Missing field model')
        if self.model and self.model not in ['ADU100', 'ADU200', 'ADU208']:
            raise ValueError('Model not supported. Supported models are: ADU100, ADU200, and ADU208')
        if 'relay0_enabled' not in cfg.keys():
            raise ValueError('Missing field relay0 enabled')
        self.relay_enabled = cfg['relay0_enabled']
        if 'relay0_mode' not in cfg.keys():
            raise ValueError('Missing field relay0 mode')
        if cfg['relay0_mode'] not in ['Switch', 'Pump']:
            raise ValueError('relay0_mode not supported. Supported models are: Switch and Pump')
        self.relay_mode = cfg['relay0_mode']
        if not self.relay_enabled:
            self.widget_flow_control_enabled = False
            self.widget_pump_control_enabled = False
        elif self.relay_mode == 'Switch':
            self.widget_flow_control_enabled = True
            self.widget_pump_control_enabled = False
            self.relay_status = RELAY_HOURLY
        elif self.relay_mode == 'Pump':
            self.widget_flow_control_enabled = False
            self.widget_pump_control_enabled = True
            self.relay_status = RELAY_HOURLY
        self._relay_interval_start = None
        self._relay_cached_position = None
        if 'event_counter_channels_enabled' not in cfg.keys():
            raise ValueError('Missing field event counter channels enabled')
        self.event_counter_channels = cfg['event_counter_channels_enabled']
        if 'event_counter_k_factors' not in cfg.keys():
            raise ValueError('Missing field event counter k factors')
        self.event_counter_k_factors = cfg['event_counter_k_factors']
        self._event_counter_past_timestamps = [float('nan')] * len(self.event_counter_channels)

        if self.model == 'ADU100':
            if 'analog_channels_enabled' not in cfg.keys():
                raise ValueError('Missing field analog channels enabled')
                self.analog_channels = cfg['analog_channels_enabled']
            if 'analog_channels_gains' not in cfg.keys():
                raise ValueError('Missing field analog channels gains')
            self.analog_gains = cfg['analog_channels_gains']
        else:
            # Prevent loading analog channels for models that don't support it
            #   => read_analog check if there is channel to reads otherwise
            self.analog_channels = []
            self.analog_gains = []
        self._analog_calibration_timestamp = None
        # Overload cfg with DATAQ specific parameters
        if self.relay_mode == 'Switch':
            relay_label, relay_units = 'Switch', '0=TOTAL|1=FILTERED'
        elif self.relay_mode == 'Pump':
            relay_label, relay_units = 'Pump', '0=OFF|1=ON'
        else:
            relay_label, relay_units = 'Relay', '0=OFF|1=ON'
        cfg['variable_names'] = ([relay_label] if self.relay_enabled else []) + \
                                [f'Flow({c})' for c in self.event_counter_channels] + \
                                [f'Analog({c})' for c in self.analog_channels]
        cfg['variable_units'] = ([relay_units] if self.relay_enabled else []) + \
                                ['L/min'] * len(self.event_counter_channels) + \
                                ['V'] * len(self.analog_channels)
        cfg['variable_precision'] = (['%s'] if self.relay_enabled else []) + \
                                    ['%.3f'] * len(self.event_counter_channels) + \
                                    ['%.6f'] * len(self.analog_channels)
        cfg['terminator'] = None  # Not Applicable
        # Set standard configuration and check cfg input
        super().setup(cfg, raw_logger)
        # Update Auxiliary Widget
        self.widget_aux_data_variable_names = []
        if self.relay_enabled:
            if self.relay_mode == 'Switch':
                self.widget_aux_data_variable_names.append('Switch')
            elif self.relay_mode == 'Pump':
                self.widget_aux_data_variable_names.append('Pump')
            else:
                self.widget_aux_data_variable_names.append('Relay')
        for c in self.event_counter_channels:
            self.widget_aux_data_variable_names.append(f'Flow #{c} (L/min)')
        for c in self.analog_channels:
            self.widget_aux_data_variable_names.append(f'Analog C{c} (V)')

    def setup_interface(self, cfg):
        if 'interface' in cfg.keys():
            if cfg['interface'] == 'usb':
                self._interface = get_adu_interface(USBInterface)()
            elif cfg['interface'] == 'usb-hid':
                self._interface = get_adu_interface(USBHIDInterface)()
            elif cfg['interface'] == 'usb-aduhid':
                self._interface = USBADUHIDInterface()
            else:
                raise ValueError(f'Invalid communication interface {cfg["interface"]}')

    def open(self, **kwargs):
        if self._interface.name.startswith('usb'):
            if self.model == 'ADU100':
                product_id = 100
            elif self.model == 'ADU200':
                product_id = 200
            elif self.model == 'ADU208':
                product_id = 208
            else:
                raise ValueError('Model not supported.')
            super().open(vendor_id=self.VENDOR_ID, product_id=product_id, **kwargs)
        else:
            super().open(**kwargs)

    def close(self, wait_thread_join=True):
        if self.relay_mode == 'Pump':
            self.relay_status = RELAY_OFF
            self.set_relay()
        super().close(wait_thread_join)

    def run(self):
        if self._interface.is_open:
            self.init_interface()
        data_timeout_flag, data_received = False, None
        while self.alive and self._interface.is_open:
            try:
                tic = time()
                # Set relay, read event counters, and analog
                relay = self.set_relay()
                ec_timestamps, ec_values = self.read_event_counters()
                analog_values = self.read_analog()
                timestamp = time()
                packet = ADUPacket(relay, ec_values, ec_timestamps, analog_values)
                if packet:
                    try:
                        self.handle_packet(packet, timestamp)
                    except Exception as e:
                        self.logger.warning(e)
                        # raise e
                toc = 1/self.refresh_rate - (time() - tic)
                if toc > 0:
                    sleep(toc)
            except InterfaceException as e:
                # probably some I/O problem such as disconnected USB serial
                # adapters -> exit
                self.logger.error(e)
                self.signal.alarm.emit(True)
                # raise e
                break
        self.close(wait_thread_join=False)

    def init_interface(self):
        """ Initialize ADU100 """
        self._interface.write('CPA1111')  # Configure Digital ports PA3, PA2, PA1, and PA0 as input for event counter
        for channel in self.event_counter_channels:
            self._interface.write(f'RC{channel}')  # Set all event counters to 0
            self._interface.read()
        self._interface.write('RPK0')
        value = self._interface.read()
        self._relay_cached_position = None if value is None else bool(value)
        if self.relay_mode == 'Pump':
            # Skip first hour
            self._relay_hourly_skip_before = time() + 3600
            # self._relay_interval_start = time() - self.relay_on_duration * 60  # Default to off on start
        else:
            self._relay_hourly_skip_before = 0
        self._relay_interval_start = time()

    def parse(self, packet: ADUPacket):
        data: List[bool, float] = [packet.relay] if self.relay_enabled else []
        for t, v, pt, k in zip(packet.event_counter_timestamps, packet.event_counter_values,
                               self._event_counter_past_timestamps, self.event_counter_k_factors):
            if isnan(pt):
                data.append(float('nan'))
            else:
                data.append(v / k * GALLONS_TO_LITERS / ((t - pt) / 60))  # liters/minutes
        self._event_counter_past_timestamps = packet.event_counter_timestamps
        for v, c, g in zip(packet.analog_values, self.analog_channels, self.analog_gains):
            data.append(v / self.ADC_RESOLUTION * self.UNIPOLAR_MAX_VOLTAGE[c][g])
        return data

    def handle_data(self, data, timestamp):
        super().handle_data(data, timestamp)
        # Format and signal aux data
        aux, i = [None] * len(data), 0
        if self.relay_enabled:
            if self.relay_mode == 'Switch':
                aux[i] = 'Filter' if data[i] else 'Total'
            else:
                aux[i] = 'On' if data[i] else 'Off'
            i += 1
        for _ in self.event_counter_channels:
            aux[i] = f'{data[i]:.2f}'
            i += 1
        for _ in self.analog_channels:
            aux[i] = f'{data[i]:.4f}'
            i += 1
        self.signal.new_aux_data.emit(aux)

    def set_relay(self):
        """
        Set relay(s)
        TODO work on interfacing relay 1, 2, and 3 on ADU20X (only relay 0) for now
        :return:
        """
        if not self.relay_enabled:
            return None
        # Get relay position
        if self.relay_status == RELAY_ON:
            set_relay = True
        elif self.relay_status == RELAY_OFF:
            set_relay = False
        elif self.relay_status == RELAY_HOURLY:
            minute = int(strftime('%M'))
            stop_at = self.relay_hourly_start_at + self.relay_on_duration
            if ((self.relay_hourly_start_at <= minute < stop_at < 60) or \
                    (60 <= stop_at and (self.relay_hourly_start_at <= minute or minute < stop_at % 60))) and \
                    self._relay_hourly_skip_before < time():
                set_relay = True
            else:
                set_relay = False
        elif self.relay_status == RELAY_INTERVAL:
            delta = ((time() - self._relay_interval_start) / 60) % (self.relay_on_duration + self.relay_off_duration)
            set_relay = (delta < self.relay_on_duration)
        else:
            raise ValueError('Invalid operation mode for relay.')
        # Set relay position
        if set_relay != self._relay_cached_position:
            if set_relay:
                self._interface.write('SK0')  # ON
                self._relay_cached_position = True
            else:
                self._interface.write('RK0')  # OFF
                self._relay_cached_position = False
        return self._relay_cached_position

    def read_event_counters(self):
        timestamps, values = [], []
        for channel in self.event_counter_channels:
            self._interface.write(f'RC{channel}')  # Read and Clean Counter
            timestamps.append(time())  # Get exact timestamp, needed to calculate flow rate
            value = self._interface.read()
            values.append(float('nan') if value is None else value)
        return timestamps, values

    def read_analog(self):
        data = []
        if not self.analog_channels:
            return data
        calibration = 'N'
        if self._analog_calibration_timestamp is None or \
                time() - self._analog_calibration_timestamp > self._analog_calibration_interval:
            calibration = 'C'
            self._analog_calibration_timestamp = time()
            self.logger.debug('Self-calibrating analog channel(s).')
        for channel, gain in zip(self.analog_channels, self.analog_gains):
            self._interface.write(f'RU{calibration}{channel}{gain}')
            value = self._interface.read()
            data.append(float('nan') if value is None else value)
        return data


def get_adu_interface(interface):
    """
    Overload Interface with ADU specifics
    :param interface:
    :return:
    """

    class ADUInterface(interface):
        def __init__(self):
            super().__init__()

        def write(self, msg_str):
            # message structure:
            #   message is an ASCII string containing the command
            #   8 bytes in lenth
            #   0th byte must always be 0x01
            #   bytes 1 to 7 are ASCII character values representing the command
            #   remainder of message is padded to character code 0 (null)
            byte_str = chr(0x01) + msg_str + chr(0) * max(7 - len(msg_str), 0)
            try:
                num_bytes_written = super().write(byte_str.encode())
            except IOError as e:
                raise InterfaceException(e)
            return num_bytes_written

        def read(self):
            try:
                # read 8-bytes from the device
                data = super().read(8)
            except IOError as e:
                raise InterfaceException(e)
            # construct a string out of the read values, starting from the 2nd byte
            byte_str = ''.join(chr(n) for n in data[1:])
            result_str = byte_str.split('\x00', 1)[0]  # remove the trailing null '\x00' characters
            if len(result_str) == 0:
                return None
            return int(result_str)  # Convert back to int

    return ADUInterface


class USBADUHIDInterface(Interface):
    """
    Use the ontrak AduHid DLL module
    Interface specific to ontrak ADU devices, will not work with other devices

    """

    def __init__(self):
        self._device = None
        self._timeout = 100  # ms
        self._serial_number = None


    @property
    def is_open(self) -> bool:
        return self._device is not None

    @property
    def timeout(self) -> int:
        return self._timeout / 1000

    @property
    def name(self) -> str:
        if self.is_open:
            return f'usb-aduhid:{self._serial_number}'
        else:
            return f'usb-aduhid'

    def open(self, vendor_id, product_id=None, serial_number=None):
        # vendor_id is ignored and set to ontrak
        if platform.system() != 'Windows':
            raise InterfaceException('USB-ADUHID interface is compatible with Windows only.')
        if product_id is not None:
            self._device = aduhid.open_device_by_product_id(product_id, self._timeout)
        elif serial_number is not None:
            self._device = aduhid.open_device_by_serial_number(serial_number, self._timeout)
        else:
            raise InterfaceException(f'ADUHID.open requires a product_id or a serial_number, none were provided.')
        if self._device is None:
            raise InterfaceException(f'ADUHID module unable to open device {product_id}.')

    def close(self):
        if self.is_open:
            aduhid.close_device(self._device)
            self._device = None

    def read(self, size=8):
        if size % 8:
            raise InterfaceException(f'ADUHID module reads in multiple of 8 bytes.')
        if self.is_open:
            if size == 8:
                r = aduhid.read_device(self._device, self._timeout)[1]
                return int(r) if r is not None else r
            result = ''
            for i in range(size/8):
                r = aduhid.read_device(self._device, self._timeout)[1]
                if r is not None:
                    result += r
            return int(result)
        raise InterfaceException(f'ADUHID module unable to read, open connection to device first.')

    def write(self, data):
        if self.is_open:
            return aduhid.write_device(self._device, data, self._timeout)
        raise InterfaceException(f'ADUHID module unable to write, open connection to device first.')
