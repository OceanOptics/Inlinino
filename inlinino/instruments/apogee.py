from time import time
from struct import unpack

from inlinino.instruments import Instrument, ModbusProtocol, InterfaceException


class ApogeeQuantumSensor(Instrument):
    REQUIRED_CFG_FIELDS = ['model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_precision']

    REG_FLOAT_CALIBRATED_MEASUREMENT = 0
    REG_FLOAT_MILLIVOLTS_MEASUREMENT = 2
    REG_FLOAT_IMMERSED_MEASUREMENT = 4
    REG_FLOAT_SOLAR_MEASUREMENT = 6
    REG_FLOAT_DEVICE_STATUS = 10
    REG_FLOAT_DEVICE_FIRMWARE = 12
    REG_FLOAT_DEVICE_MODEL = 18
    REG_FLOAT_DEVICE_SERIAL_NUMBER = 20
    REG_FLOAT_CAL_MULTIPLITER = 28
    REG_FLOAT_CAL_OFFSET = 30
    REG_FLOAT_IMMERSION_COEF = 32
    REG_FLOAT_SOLAR_MULTIPLIER = 34
    REG_INT_CALIBRATED_MEASUREMENT = 40

    def __init__(self, uuid, cfg, signal, *args, **kwargs):
        super().__init__(uuid, cfg, signal, *args, **kwargs)

        # Protocol
        self.protocol = ModbusProtocol(b'\x01')

        # Default serial communication parameters
        self.default_serial_baudrate = 19200
        self.default_serial_parity = 'even'
        self.default_serial_timeout = 0.1

        # Auxiliary Data widget
        self.widget_aux_data_enabled = True
        self.widget_aux_data_variable_names = ['PAR (umol/m2/s)']

    def setup(self, cfg):
        # Instrument specific configuration
        cfg['variable_names'] = ['PAR']
        cfg['variable_units'] = ['umol/m2/s']
        cfg['variable_precision'] = ['%.5f']
        cfg['terminator'] = b''  # Not used due to the nature of the modbus protocol
        # Set standard configuration and check cfg input
        super().setup(cfg)

    def init_interface(self):
        # TODO Query model, serial number, calibration coefficients
        self.request_packet()

    def run(self):
        # Overwrite run as no frame terminator
        # Assume that if no data more data received then received complete frame
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
                if len(data) > 0:
                    # If data extend buffer (until no more data is coming)
                    self._buffer.extend(data)
                    # Update no data timeout
                    data_received = timestamp
                    if data_timeout_flag:
                        data_timeout_flag = False
                        if self.signal.alarm is not None:
                            self.signal.alarm.emit(False)
                else:
                    if len(self._buffer) > 0:
                        # No new data so assume we received complete packet
                        self.data_received(data, timestamp)
                    # Update no data timeout
                    if data_received is not None and \
                            timestamp - data_received > self.DATA_TIMEOUT and data_timeout_flag is False:
                        self.logger.error(
                            f'No data received during the past {timestamp - data_received:.2f} seconds')
                        data_timeout_flag = True
                        if self.signal.alarm is not None:
                            self.signal.alarm.emit(True)
                if len(self._buffer) == 0:
                    # Request new data if buffer is empty (as no way to detect end of frame)
                    self.request_packet()
                elif len(self._buffer) > self._max_buffer_length:
                    self.logger.warning('Buffer exceeded maximum length. Buffer emptied to prevent overflow')
                    self._buffer = bytearray()
            except InterfaceException as e:
                # probably some I/O problem such as disconnected USB serial
                # adapters -> exit
                self.logger.error(e)
                if self.signal.alarm is not None:
                    self.signal.alarm.emit(True)
                break
            except Exception as e:
                self.logger.warning(e)
                # raise e
        self.close(wait_thread_join=False)

    def data_received(self, _, timestamp):
        # Assume received complete packet
        packet = self._buffer
        self._buffer = bytearray()
        try:
            self.handle_packet(packet, timestamp)
        except (ValueError, NotImplementedError) as e:
            self.signal.packet_corrupted.emit()
            self.logger.warning(e)
            self.logger.debug(packet)
            # raise e

    def request_packet(self):
        # Should be using parent method write_to_interface. However, write_to_interface is called at
        #   the incorrect time in handle_packet
        req = self.protocol.request(self.REG_FLOAT_CALIBRATED_MEASUREMENT, 2)  # Float requires two 16-bits registers
        # req = self.protocol.request(self.REG_INT_CALIBRATED_MEASUREMENT, 1)  # Int requires one 16-bits register
        self._interface.write(req)

    def parse(self, packet):
        value: bytearray = self.protocol.handle_response(packet)
        return unpack('>f', value)  # Float register
        # return int.from_bytes(value, 'big')  # Int Register

    def handle_data(self, data, timestamp):
        super().handle_data(data, timestamp)
        # Format and signal aux data
        self.signal.new_aux_data.emit([f"{data[0]:.3f}"])
