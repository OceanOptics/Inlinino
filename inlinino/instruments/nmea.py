from inlinino.instruments import Instrument
import numpy as np
import pynmea2


class NMEA(Instrument):

    REQUIRED_CFG_FIELDS = ['model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_types', 'variable_precision']

    def __init__(self, uuid, cfg, signal, *args, **kwargs):
        self.active_timeseries_variables = []
        self.widget_active_timeseries_variables_selected = list()
        self._unknown_nmea_sentence = []
        super().__init__(uuid, cfg, signal, *args, **kwargs)

        # Default serial communication parameters
        self.default_serial_baudrate = 4800
        self.default_serial_timeout = 10

    def setup(self, cfg):
        # Overload cfg
        cfg['terminator'] = b'\r\n'
        # Set standard configuration and check cfg input
        super().setup(cfg)
        # Set active timeseries variables
        self.active_timeseries_variables = np.zeros(len(self.variable_types), dtype=bool)
        self.widget_active_timeseries_variables_selected = list()
        for i, (k, t) in enumerate(zip(self.variable_names, self.variable_types)):
            if t in ['int', 'float']:
                self.active_timeseries_variables[i] = True
                self.widget_active_timeseries_variables_selected.append(k)
        # self._log_prod.variable_precision = []  # Disable precision when writing with log

    # def open(self, port=None, baudrate=4800, bytesize=8, parity='N', stopbits=1, timeout=10):
    #     super().open(port, baudrate, bytesize, parity, stopbits, timeout)

    def parse(self, packet):
        data = [float('nan')] * len(self.variable_names)
        try:
            msg = pynmea2.parse(packet.decode())
        except ValueError:
            return data
        # MWV special parsing
        if msg.sentence_type == 'MWV':
            for i, k in enumerate(self.variable_names):
                if msg.reference == 'R':  # apparent wind
                    if k == 'wind_speed_apparent':
                        data[i] = float(msg.wind_speed)
                    elif k == 'wind_angle_apparent':
                        data[i] = float(msg.wind_angle)
                elif msg.reference == 'T':  # true wind
                    if k == 'wind_speed_true':
                        data[i] = float(msg.wind_speed)
                    elif k == 'wind_angle_true':
                        data[i] = float(msg.wind_angle)
            return data
        # Default parsing
        for i, (k, t) in enumerate(zip(self.variable_names, self.variable_types)):
            if not hasattr(msg, k):
                continue
            value = getattr(msg, k)
            if value in ['', None]:
                continue
            if t == 'int':
                data[i] = int(value)
            elif t == 'float':
                data[i] = float(value)
            elif t == 'str':
                data[i] = str(value)
            else:
                raise ValueError("Variable type not supported. Correct Instrument Setup > Variable Types.")
        return data

    def handle_data(self, data, timestamp):
        if np.any(self.active_timeseries_variables):
            self.signal.new_ts_data.emit(np.array(data)[self.active_timeseries_variables], timestamp)
        if self.log_prod_enabled and self._log_active:
            self._log_prod.write(data, timestamp)
            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()