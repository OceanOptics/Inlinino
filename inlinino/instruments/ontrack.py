from time import time, sleep, strftime
from dataclasses import dataclass, field
from typing import List
from math import isnan

import usb.core

from inlinino.instruments import Instrument, USBInterface, USBHIDInterface, InterfaceException
from inlinino.log import LogText

SWITCH_FORCE_OFF = 0
SWITCH_FORCE_ON = 1
SWITCH_HOURLY = 2
SWITCH_INTERVAL = 3
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


class Ontrack(Instrument):
    """
    Ontrack Control Systems Data Acquisition Interface
    Supported Model: ADU100
    """

    VENDOR_ID = 0x0a07
    PRODUCT_ID = 100
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

    REQUIRED_CFG_FIELDS = ['relay_enabled',
                           'event_counter_channels_enabled', 'event_counter_k_factors',
                           'analog_channels_enabled', 'analog_channels_gains',
                           'model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_precision']

    def __init__(self, cfg_id, signal, *args, **kwargs):
        super().__init__(cfg_id, signal, *args, setup=False, **kwargs)
        # Instrument Specific attributes
        # Relay
        self.relay_enabled = True
        # TODO Store four parameters below in configuration file to replicate main interface
        self.relay_mode = SWITCH_HOURLY
        self.relay_hourly_start_at = 0   # minutes
        self.relay_on_duration = 10      # minutes
        self.relay_interval_every = 30   # minutes
        self._relay_interval_start = None
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
        # Init Auxiliary Data Plugin
        self.plugin_aux_data = True
        self.plugin_aux_data_variable_names = []
        # Init Flow Control Plugin
        # TODO NEED TO KNOW IF RELAY IS CONNECTED
        self.secondary_dock_widget_enabled = True
        self.plugin_instrument_control_enabled = True
        # Setup
        self.init_setup()

    def setup(self, cfg, raw_logger=LogText):
        # Set specific attributes
        if 'relay_enabled' not in cfg.keys():
            raise ValueError('Missing field relay enabled')
        self.relay_enabled = cfg['relay_enabled']
        self._relay_interval_start = None
        self._relay_cached_position = None
        if 'event_counter_channels_enabled' not in cfg.keys():
            raise ValueError('Missing field event counter channels enabled')
        self.event_counter_channels = cfg['event_counter_channels_enabled']
        if 'event_counter_k_factors' not in cfg.keys():
            raise ValueError('Missing field event counter k factors')
        self.event_counter_k_factors = cfg['event_counter_k_factors']
        self._event_counter_past_timestamps = [float('nan')] * len(self.event_counter_channels)
        if 'analog_channels_enabled' not in cfg.keys():
            raise ValueError('Missing field analog channels enabled')
        self.analog_channels = cfg['analog_channels_enabled']
        if 'analog_channels_gains' not in cfg.keys():
            raise ValueError('Missing field analog channels gains')
        self.analog_gains = cfg['analog_channels_gains']
        self._analog_calibration_timestamp = None
        # Overload cfg with DATAQ specific parameters
        cfg['variable_names'] = (['Switch'] if self.relay_enabled else []) + \
                                [f'Flow({c})' for c in self.event_counter_channels] + \
                                [f'Analog({c})' for c in self.analog_channels]
        cfg['variable_units'] = (['True=FILTERED|False=TOTAL'] if self.relay_enabled else []) + \
                                ['L/min'] * len(self.event_counter_channels) + \
                                ['V'] * len(self.analog_channels)
        cfg['variable_precision'] = (['%s'] if self.relay_enabled else []) + \
                                    ['%.3f'] * len(self.event_counter_channels) + \
                                    ['%.6f'] * len(self.analog_channels)
        cfg['terminator'] = None  # Not Applicable
        # Set standard configuration and check cfg input
        super().setup(cfg, raw_logger)
        # Update interface
        self._interface = ADUHIDAPIInterface()
        # Update Auxiliary Plugin
        self.plugin_aux_data_variable_names = []
        if self.relay_enabled:
            self.plugin_aux_data_variable_names.append('Switch')
        for c in self.event_counter_channels:
            self.plugin_aux_data_variable_names.append(f'Flow #{c} (L/min)')
        for c in self.analog_channels:
            self.plugin_aux_data_variable_names.append(f'Analog C{c} (V)')

    def open(self, **kwargs):
        super().open(vendor_id=self.VENDOR_ID, product_id=self.PRODUCT_ID, **kwargs)

    def run(self):
        if self._interface.is_open:
            self.init_interface()
        data_timeout_flag, data_received = False, None
        while self.alive and self._interface.is_open:
            try:
                tic = time()
                # Set relay, read event counters and analog
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
            aux[i] = 'Filter' if data[i] else 'Total'
            i += 1
        for _ in self.event_counter_channels:
            aux[i] = f'{data[i]:.2f}'
            i += 1
        for _ in self.analog_channels:
            aux[i] = f'{data[i]:.4f}'
            i += 1
        self.signal.new_aux_data.emit(aux)

    def set_relay(self):
        if not self.relay_enabled:
            return None
        # Get relay position
        if self.relay_mode == SWITCH_FORCE_ON:
            set_relay = True
        elif self.relay_mode == SWITCH_FORCE_OFF:
            set_relay = False
        elif self.relay_mode == SWITCH_HOURLY:
            minute = int(strftime('%M'))
            stop_at = self.relay_hourly_start_at + self.relay_on_duration
            if (self.relay_hourly_start_at <= minute < stop_at < 60) or \
                    (60 <= stop_at and (self.relay_hourly_start_at <= minute or minute < stop_at % 60)):
                set_relay = True
            else:
                set_relay = False
        elif self.relay_mode == SWITCH_INTERVAL:
            if self._relay_interval_start is None:
                self._relay_interval_start = time()
            delta = ((time() - self._relay_interval_start) / 60) % (self.relay_interval_every + self.relay_on_duration)
            set_relay = True if delta < self.relay_interval_every else False
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
            timestamps.append(time())  # Get exact timestamp, needed to calculate flowrate
            value = self._interface.read()
            values.append(float('nan') if value is None else int(value))
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
            data.append(float('nan') if value is None else int(value))
        return data


class ADULibUSBInterface(USBInterface):
    def __init__(self):
        super().__init__()
        self.read_endpoint, self.read_size, self.write_endpoint = 0x81, 64, 0x01

    def write(self, msg_str):
        # message structure:
        #   message is an ASCII string containing the command
        #   8 bytes in lenth
        #   0th byte must always be 0x01
        #   bytes 1 to 7 are ASCII character values representing the command
        #   remainder of message is padded to character code 0 (null)
        byte_str = chr(0x01) + msg_str + chr(0) * max(7 - len(msg_str), 0)
        num_bytes_written = 0
        try:
            num_bytes_written = self._device.write(self.write_endpoint, byte_str)
        except usb.core.USBError as e:
            raise InterfaceException(e)
        return num_bytes_written

    def read(self):
        try:
            data = self._device.read(self.read_endpoint, self.read_size, self._timeout)
        except usb.core.USBError as e:
            raise InterfaceException(e)
        # construct a string out of the read values, starting from the 2nd byte
        byte_str = ''.join(chr(n) for n in data[1:])
        result_str = byte_str.split('\x00', 1)[0]  # remove the trailing null '\x00' characters
        if len(result_str) == 0:
            return None
        return result_str


class ADUHIDAPIInterface(USBHIDInterface):
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
            num_bytes_written = self._device.write(byte_str.encode())
        except IOError as e:
            raise InterfaceException(e)
        return num_bytes_written

    def read(self):
        try:
            # read a maximum of 8 bytes from the device, with a user specified timeout
            data = self._device.read(8, self._timeout)
        except IOError as e:
            raise InterfaceException(e)
        # construct a string out of the read values, starting from the 2nd byte
        byte_str = ''.join(chr(n) for n in data[1:])
        result_str = byte_str.split('\x00', 1)[0]  # remove the trailing null '\x00' characters
        if len(result_str) == 0:
            return None
        return result_str
