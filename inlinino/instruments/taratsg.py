from inlinino.instruments import Instrument


class TaraTSG(Instrument):

    REQUIRED_CFG_FIELDS = ['model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_precision']

    def setup(self, cfg):
        # Overload cfg with Tara TSG specific parameters
        cfg['variable_names'] = ['t1', 'c1', 's', 't2']
        cfg['variable_units'] = ['degC', 'S/m', 'psu', 'degC']
        cfg['variable_precision'] = ['%.4f', '%.5f', '%.4f', '%.4f']
        cfg['terminator'] = b'\r\n'
        # Set standard configuration and check cfg input
        super().setup(cfg)

    def open(self, port=None, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=3):
        super().open(port, baudrate, bytesize, parity, stopbits, timeout)

    def parse(self, packet):
        foo = packet.split(b',')
        bar = [0.0] * 4
        for i in range(4):
            bar[i] = float(foo[i].split(b'=')[1])
        return bar