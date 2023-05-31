from inlinino.instruments import Instrument


class TaraTSG(Instrument):

    REQUIRED_CFG_FIELDS = ['model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_precision']

    def __init__(self, uuid, cfg, signal, *args, **kwargs):
        super().__init__(uuid, cfg, signal, *args, **kwargs)

        # Default serial communication parameters
        self.default_serial_baudrate = 9600
        self.default_serial_timeout = 3

        # Auxiliary Data widget
        self.widget_aux_data_enabled = True
        self.widget_aux_data_variable_names = ['Temp. 1 (ºC)', 'Temp. 2 (ºC)', 'Cond. 1 (S/m)', 'Salinity (psu)']

    def setup(self, cfg):
        # Overload cfg with Tara TSG specific parameters
        cfg['variable_names'] = ['t1', 'c1', 's', 'sv', 't2']
        cfg['variable_units'] = ['degC', 'S/m', 'psu', 'm/s', 'degC']
        cfg['variable_precision'] = ['%.4f', '%.5f', '%.4f', '%.3f', '%.4f']
        cfg['terminator'] = b'\r\n'
        # Set standard configuration and check cfg input
        super().setup(cfg)

    # def open(self, port=None, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=3):
    #     super().open(port, baudrate, bytesize, parity, stopbits, timeout)

    def parse(self, packet):
        foo = packet.split(b',')
        bar = [float('nan')] * 5
        for i in range(min(5, len(foo))):
            if b'=' in foo[i]:
                bar[i] = float(foo[i].split(b'=')[1])
            else:
                bar[i] = float(foo[i])
        return bar

    def handle_data(self, data, timestamp):
        super().handle_data(data, timestamp)
        # Format and signal aux data
        self.signal.new_aux_data.emit(['%.4f' % data[0], '%.4f' % data[4],
                                       '%.4f' % data[1], '%.4f' % data[2]])
