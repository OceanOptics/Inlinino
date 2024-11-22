from time import time, sleep, strftime
from dataclasses import dataclass, field
from typing import List, Dict, Union
from math import isnan
import platform

from inlinino.instruments import Instrument, USBInterface, USBHIDInterface, InterfaceException, Interface
from inlinino.log import LogText

if platform.system() == 'Windows':
    try:
        from inlinino.resources.ontrak import aduhid
    except ImportError:
        aduhid = None
else:
    aduhid = None


GALLONS_TO_LITERS = 3.78541


@dataclass
class ADUPacket:
    relays: List[bool] = field(default_factory=list)
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
        repr = ','.join(self.relays)
        for t, v in zip(self.event_counter_timestamps, self.event_counter_values):
            repr += f',{t},{v}' if repr else f'{t},{v}'
        repr += (',' if repr else '') + ','.join(self.analog_values)
        return repr

    def __bool__(self):
        if self.relays or self.event_counter_values or self.analog_values:
            return True
        return False


class Ontrak(Instrument):
    """
    ontrak Control Systems Data Acquisition Interface
    """

    VENDOR_ID = 0x0a07

    SUPPORTED_MODELS = ['ADU100', 'ADU200', 'ADU208', 'ADU222']

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
        self.relays_enabled = []
        self.relays_gui_mode: Union[List[str], List[None]] = [None] * 4
        self.relays: Union[List[Relay], List[None]] = [None] * 4
        # Event Counter(s) / Flowmeter(s)
        self.event_counter_channels = [0]
        self.event_counter_k_factors = [1381]
        self._event_counter_past_timestamps = [float('nan')] * len(self.event_counter_channels)
        # Low Flow Alarm
        self.low_flow_alarm_enabled = True
        self._low_flow_alarm_started = False
        self._low_flow_alarm_on = False
        self._low_flow_alarm_on_counter = 0
        self._low_flow_alarm_off_counter = 0
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
        self.widget_flow_controls_enabled: Union[List[bool], List[None]] = [None] * 4
        self.widget_pump_controls_enabled: Union[List[bool], List[None]] = [None] * 4
        self.widgets_to_load: List[str] = ['FlowControlWidget'] * 4 + ['PumpControlWidget'] * 4
        self.widgets_to_load_kwargs: List[Dict] = [{'id': k} for k in range(4)] * 2
        # Setup
        self.setup(cfg)

    def setup(self, cfg, raw_logger=LogText):
        # Set specific attributes
        if 'model' not in cfg.keys():
            raise ValueError('Missing field model')
        if self.model and self.model not in Ontrak.SUPPORTED_MODELS:
            raise ValueError(f"Model not supported. Supported models are: {', '.join(Ontrak.SUPPORTED_MODELS)}")
        # Relays
        n_relays = 4
        relay_mode_supported = ['Switch', 'Switch (one-wire)', 'Switch (two-wire)', 'Pump']
        if cfg['model'] == 'ADU100':
            n_relays = 1
            relay_mode_supported.remove('Switch (two-wire)')
        elif cfg['model'] == 'ADU222':
            n_relays = 2
        self.relays_enabled, self.relays_gui_mode, self.relays = [], [None]*4, [None]*4
        self.widget_flow_controls_enabled, self.widget_pump_controls_enabled = [None]*4, [None]*4
        for r in range(n_relays):
            if f'relay{r}_enabled' in cfg.keys() and cfg[f'relay{r}_enabled']:
                self.relays_enabled.append(r)
            else:
                self.relays_gui_mode[r] = None
                self.relays[r] = None
                self.widget_flow_controls_enabled[r] = False
                self.widget_pump_controls_enabled[r] = False
                continue
            if f'relay{r}_mode' in cfg.keys():
                if cfg[f'relay{r}_mode'] not in relay_mode_supported:
                    raise ValueError(f"{cfg[f'relay{r}_mode']} not supported by {cfg['model']}.")
                self.relays_gui_mode[r] = cfg[f'relay{r}_mode']
            else:
                raise ValueError(f'Missing field relay{r} mode')
            self.relays[r] = CoupledExpiringRelay(r, r+1) if 'two-wire' in self.relays_gui_mode[r] else Relay(r)
            self.relays[r].mode = Relay.HOURLY
            if self.relays_gui_mode[r].startswith('Switch'):
                self.widget_flow_controls_enabled[r] = True
                self.widget_pump_controls_enabled[r] = False
            elif self.relays_gui_mode[r] == 'Pump':
                self.widget_flow_controls_enabled[r] = False
                self.widget_pump_controls_enabled[r] = True
        # Event Counters
        if cfg['model'] != 'ADU222':
            if 'event_counter_channels_enabled' not in cfg.keys():
                raise ValueError('Missing field event counter channels enabled')
            self.event_counter_channels = cfg['event_counter_channels_enabled']
            if 'event_counter_k_factors' not in cfg.keys():
                raise ValueError('Missing field event counter k factors')
            self.event_counter_k_factors = cfg['event_counter_k_factors']
            self._event_counter_past_timestamps = [float('nan')] * len(self.event_counter_channels)
            if 'low_flow_alarm_enabled' in cfg.keys():
                self.low_flow_alarm_enabled = cfg['low_flow_alarm_enabled']
        else:
            self.event_counter_channels = []
            self.event_counter_k_factors = []
            self._event_counter_past_timestamps = []
            self.low_flow_alarm_enabled = False
        # Analog Channels
        if cfg['model'] == 'ADU100':
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
        relays_label, relays_units = [], []
        for r in self.relays_enabled:
            if self.relays_gui_mode[r].startswith('Switch'):
                relays_label.append(f'Switch({r})'), relays_units.append('0=TOTAL|1=FILTERED')
            elif self.relays_gui_mode[r] == 'Pump':
                relays_label.append(f'Pump({r})'), relays_units.append('0=OFF|1=ON')
            else:
                relays_label.append(f'Relay({r})'), relays_units.append('0=OFF|1=ON')
        cfg['variable_names'] = relays_label + \
                                [f'Flow({c})' for c in self.event_counter_channels] + \
                                [f'Analog({c})' for c in self.analog_channels]
        cfg['variable_units'] = relays_units + \
                                ['L/min'] * len(self.event_counter_channels) + \
                                ['V'] * len(self.analog_channels)
        cfg['variable_precision'] = ['%s'] * len(self.relays_enabled) + \
                                    ['%.3f'] * len(self.event_counter_channels) + \
                                    ['%.6f'] * len(self.analog_channels)
        cfg['terminator'] = None  # Not Applicable
        # Set standard configuration and check cfg input
        super().setup(cfg, raw_logger)
        # Update Auxiliary Widget
        self.widget_aux_data_variable_names = []
        for r in self.relays_enabled:
            if self.relays_gui_mode[r].startswith('Switch'):
                self.widget_aux_data_variable_names.append(f'Switch #{r}')
            elif self.relays_gui_mode[r] == 'Pump':
                self.widget_aux_data_variable_names.append(f'Pump #{r}')
            else:
                self.widget_aux_data_variable_names.append(f'Relay #{r}')
        for c in self.event_counter_channels:
            self.widget_aux_data_variable_names.append(f'Flow #{c} (L/min)')
            self.widget_aux_data_variable_names.append(f'Flow Status #{c}')
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
            if self.model in Ontrak.SUPPORTED_MODELS:
                product_id = int(self.model[3:])
            else:
                raise ValueError('Model not supported.')
            super().open(vendor_id=self.VENDOR_ID, product_id=product_id, **kwargs)
        else:
            super().open(**kwargs)

    def close(self, wait_thread_join=True):
        for r in self.relays_enabled:
            if self.relays_gui_mode[r] == 'Pump':
                self.relays[r].mode = Relay.OFF
                self.set_relays()
        super().close(wait_thread_join)

    def run(self):
        if self._interface.is_open:
            self.init_interface()
        data_timeout_flag, data_received = False, None
        while self.alive and self._interface.is_open:
            try:
                tic = time()
                # Set relay, read event counters, and analog
                relays = self.set_relays()
                ec_timestamps, ec_values = self.read_event_counters()
                analog_values = self.read_analog()
                timestamp = time()
                packet = ADUPacket(relays, ec_values, ec_timestamps, analog_values)
                if packet:
                    try:
                        self.handle_packet(packet, timestamp)
                    except Exception as e:
                        self.logger.warning(e)
                        # raise e
                toc = 1/self.refresh_rate - (time() - tic)
                if toc > 0:
                    sleep(toc)
            except IOError as e:
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
        for r in self.relays_enabled:
            self.relays[r].read(self._interface)
            if self.relays_gui_mode[r] == 'Pump':
                # Skip first hour
                self.relays[r].hourly_skip_before = time() + 3600
                # self.relay.interval_start = time() - self.relay_on_duration * 60  # Default to off on start
            else:
                self.relays[r].hourly_skip_before = 0
            self.relays[r].interval_start = time()
        # Reset low flow alarm
        self._low_flow_alarm_started = False
        self._low_flow_alarm_on = False

    def parse(self, packet: ADUPacket):
        data: List[bool, float] = []
        data.extend(packet.relays)
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
        aux, i = [None] * len(self.widget_aux_data_variable_names), 0
        for r in self.relays_enabled:
            if self.relays_gui_mode[r].startswith('Switch'):
                aux[i] = 'Filter' if data[i] else 'Total'
            else:
                aux[i] = 'On' if data[i] else 'Off'
            i += 1
        ii = i
        for _ in self.event_counter_channels:
            aux[ii] = f'{data[i]:.2f}'
            ii += 1
            if data[i] < 1.0 or self._low_flow_alarm_on:
                aux[ii] = 'CRITICAL'
            elif data[i] < 2.0:
                aux[ii] = 'WARNING'
            else:
                aux[ii] = 'OK'
            ii += 1
            i += 1
        for _ in self.analog_channels:
            aux[ii] = f'{data[i]:.4f}'
            ii += 1
            i += 1
        self.signal.new_aux_data.emit(aux)
        # Set low flow alarm
        #   flow must be detected to enable alarm (prevent alarm to rig when connect ADU)
        #   alarm is triggered after three consecutive flow below the threshold
        #   alarm is disabled after 30 consecutive flow above threshold
        if self.low_flow_alarm_enabled:
            i = len(self.relay_enabled)
            low_flow_detected = False
            for _ in self.event_counter_channels:
                if self._low_flow_alarm_started:
                    if data[i] < 2.0:
                        low_flow_detected = True
                        break
                elif data[i] > 0.1:
                    self._low_flow_alarm_started = True
                    break
                i += 1
            if not self._low_flow_alarm_started:
                return
            if low_flow_detected:
                self._low_flow_alarm_on_counter += 1
                self._low_flow_alarm_off_counter = 0
            else:
                self._low_flow_alarm_on_counter = 0
                self._low_flow_alarm_off_counter += 1
            if not self._low_flow_alarm_on and self._low_flow_alarm_on_counter > 120:
                self._low_flow_alarm_on = True
                self.signal.alarm_custom.emit('Low flow (<2 L/min).', 'Possible issues:\n'
                                              '    - filter is full, replace filter\n'
                                              '    - pump is too slow, adjust back pressure\n')
            # elif self._low_flow_alarm_on and self._low_flow_alarm_off_counter > 20:
            #     self._low_flow_alarm_on = False

    def set_relays(self):
        """
        Set relay(s)
        :return:
        """
        return [self.relays[r].set(self._interface) for r in self.relays_enabled]

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
            num_bytes_written = super().write(byte_str.encode())
            return num_bytes_written

        def read(self):
            # read 8-bytes from the device
            data = super().read(8)
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
        if aduhid is None:
            raise InterfaceException('USB-ADUHID driver not found.')
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


class Relay:
    OFF = 0
    ON = 1
    HOURLY = 2
    INTERVAL = 3
    
    def __init__(self, id: int, mode=None):
        self.id = id  # Must be between 0 and 7
        self.mode = Relay.HOURLY if mode is None else mode

        self.hourly_start_at = 0  # minutes
        self.on_duration = 10  # minutes
        self.off_duration = 30  # minutes
        self.interval_start = None
        self.hourly_skip_before = 0

        self._cached_position = None

    def reset(self):
        self.interval_start = None
        self._cached_position = None

    def set(self, interface):
        """
        Set relay position

        :return:
        """
        if self.mode == Relay.ON:
            position = True
        elif self.mode == Relay.OFF:
            position = False
        elif self.mode == Relay.HOURLY:
            minute = int(strftime('%M'))
            stop_at = self.hourly_start_at + self.on_duration
            if (((self.hourly_start_at <= minute < stop_at < 60) or 
                (60 <= stop_at and (self.hourly_start_at <= minute or minute < stop_at % 60))) and
                self.hourly_skip_before < time()):
                position = True
            else:
                position = False
        elif self.mode == Relay.INTERVAL:
            delta = ((time() - self.interval_start) / 60) % (self.on_duration + self.off_duration)
            position = (delta < self.on_duration)
        else:
            raise ValueError('Invalid relay mode. Must be ON, OFF, HOURLY, or INTERVAL')
        self._write(position, interface)
        return position
        
    def _write(self, position, interface):
        """
        Write relay position to interface
        
        :param position: 
        :return: 
        """
        if position != self._cached_position:
            if position:
                interface.write(f'SK{self.id}')  # ON
                self._cached_position = True
            else:
                interface.write(f'RK{self.id}')  # OFF
                self._cached_position = False

    def read(self, interface):
        interface.write(f'RPK{self.id}')
        value = interface.read()
        self._cached_position = None if value is None else bool(value)


class CoupledExpiringRelay(Relay):
    """
    Coupled Relay, will have two relays in opposite position
    Both relays go back to off after "hold_on" duration expires
    
    """
    def __init__(self, id_a: int, id_b: int, mode=None):
        super().__init__(id_a, mode)
        self.id_b = id_b
        self._cached_position_b = None
        self.hold_on = 25 # seconds
        self._hold_on_start_time = None
        self._trigger_position = None

    def reset(self):
        super().reset()
        self._cached_position_b = None
        self._trigger_position = None

    def _write(self, position, interface):
        if position != self._trigger_position:
            if position:
                interface.write(f'RK{self.id_b}')  # OFF
                self._cached_position_b = False
                sleep(0.01)  # 10 ms
                interface.write(f'SK{self.id}')  # ON
                self._cached_position = True
            else:
                interface.write(f'RK{self.id}')  # OFF
                self._cached_position = False
                sleep(0.01)  # 10 ms
                interface.write(f'SK{self.id_b}')  # ON
                self._cached_position_b = True
            self._trigger_position = position
            self._hold_on_start_time = time()
        if self._hold_on_start_time is not None and time() - self._hold_on_start_time > self.hold_on:
            # Set back to off after hold_on period expires
            if self._cached_position:
                interface.write(f'RK{self.id}')  # OFF
                self._cached_position = False
            if self._cached_position_b:
                interface.write(f'RK{self.id_b}')  # OFF
                self._cached_position_b = False
