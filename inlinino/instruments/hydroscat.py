import os

from inlinino.instruments import Instrument
from inlinino.log import Log

try:
    import aquasense.hydroscat
except ImportError:
    pass

from datetime import datetime

import io
import numpy as np

from threading import Lock


class HydroScat(Instrument):

    REQUIRED_CFG_FIELDS = ['calibration_file', 'model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'burst_mode',
                           'sleep_on_memory_full',
                           'fluorescence',
                           'start_delay', 'warmup_time',
                           'burst_duration', 'burst_cycle',
                           'total_duration', 'log_period',
                           'output_cal_header',
                           'variable_names', 'variable_units', 'variable_precision']

    def __init__(self, uuid, cfg, *args, **kwargs):
        super().__init__(uuid, cfg, *args, setup=False, **kwargs)
        # Interface (specific to aquasense package, setup_interface should not update interface)
        self._io = io.TextIOWrapper(io.BufferedRWPair(self._interface._serial, self._interface._serial))

        # Instrument state machine
        self.hydroscat: aquasense.hydroscat.HydroScat = None
        self.output_cal_header = None
        self.state = "IDLE"
        self.previous_state = None

        # Default serial communication parameters
        self.default_serial_baudrate = 9600
        self.default_serial_timeout = 1

        # Auxiliary Data Plugin
        self.widget_aux_data_enabled = True
        self.widget_aux_data_variable_names = ['Temp. (ºC)', 'Depth (m)', 'Voltage (V)', 'Time']

        # Init Channels to Plot widget
        self.widget_select_channel_enabled = True
        self.widget_active_timeseries_variables_names = []
        self.widget_active_timeseries_variables_selected = []
        self.active_timeseries_variables_lock = Lock()
        self.active_variables = None

        # Init Spectrum Plot widget
        self.spectrum_plot_enabled = True
        self.spectrum_plot_axis_labels = dict(y_label_name='Signal')
        self.spectrum_plot_trace_names = ["beta"]
        self.spectrum_plot_x_values = []

        # Setup
        self.setup(cfg)

    def setup(self, cfg):
        # sanity check
        errmsgs = []
        try:
            if int(cfg["fluorescence"]) not in [0, 1, 2]:
                errmsgs.append("fluorescence must be 0, 1, or 2")
        except ValueError:
            errmsgs.append("fluorescence must be 0, 1, or 2")
        for varname in ["start_delay", "warmup_time",
                        "burst_duration", "burst_cycle",
                        "total_duration", "log_period"]:
            try:
                if float(cfg[varname]) < 0:
                    errmsgs.append("{} must be 0 or more".format(varname))
            except ValueError:
                errmsgs.append("{} must be 0 or more".format(varname))
        if not os.path.isfile(cfg["calibration_file"]):
            errmsgs.append(f"Calibration file not found: {cfg['calibration_file']}")
        if errmsgs:
            raise ValueError('\n'.join(errmsgs))

        self.hydroscat = aquasense.hydroscat.HydroScat(
                            cal_path=cfg["calibration_file"], in_out=self._io,
                            out=None, sep=",", serial_mode=False,
                            burst_mode=cfg["burst_mode"],
                            sleep_on_memory_full=cfg["sleep_on_memory_full"],
                            fluorescence_control=int(cfg["fluorescence"]),
                            start_delay=float(cfg["start_delay"]),
                            warmup_time=float(cfg["warmup_time"]),
                            burst_duration=float(cfg["burst_duration"]),
                            burst_cycle=float(cfg["burst_cycle"]),
                            total_duration=float(cfg["total_duration"]),
                            log_period=float(cfg["log_period"]),
                            output_cal_header=cfg["output_cal_header"],
                            logger=self.logger,
                            verbose=True)

        # Overload cfg with HydroScat specific parameters
        cfg['variable_names'] = ["Depth", "Voltage"] + self.hydroscat.channel_names()
        cfg['variable_units'] = ["m", "V"] + ['beta' for n in range(2, len(cfg['variable_names']))]
        cfg['variable_precision'] = ['%0.3f']*2 + \
            ['%.9f' for n in range(2, len(cfg['variable_names']))]
        cfg['terminator'] = b'\r\n'

        self.output_cal_header = cfg["output_cal_header"]

        # Active Timeseries Variables
        self.active_variables = {var_name:True for var_name in cfg['variable_names']}
        self.active_variables["Depth"] = False
        self.active_variables["Voltage"] = False
        self.widget_active_timeseries_variables_names = cfg['variable_names']
        self.widget_active_timeseries_variables_selected = \
                    [name for name in self.active_variables if self.active_variables[name]]
                
        # Update wavelengths for Spectrum Plot
        # Plot is updated after the initial instrument setup or button click
        # We only show values for bb channels since bb and fl channel numbers overlap
        betawavs = [int(betalab[2:])
                    for betalab in cfg['variable_names'] if betalab.startswith("bb")]
        self.spectrum_plot_x_values = [np.array(sorted(betawavs))]

        super().setup(cfg)

        # Set prod logger
        log_cfg = {'path': cfg['log_path'], 'filename_prefix': self.bare_log_prefix}
        for k in ['length', 'variable_names', 'variable_units', 'variable_precision']:
            if k in cfg.keys():
                log_cfg[k] = cfg[k]

        if self.output_cal_header:
            header_lines = self.hydroscat.header_lines()
        else:
            header_lines = []

        self._log_prod = ProdLogger(header_lines, log_cfg, self.signal.status_update)

    # State machine
    #  start_state =>
    #  IDLE =open button/start command=> START =>
    #  RUNNING =close button=> STOP =/stop command=> IDLE

    def change_state(self, state):
        self.previous_state = self.state
        self.state = state
        self.logger.info("{} -> {}".format(self.previous_state, state))


    def init_interface(self):
        # invoked after channel open request (via Open button)
        self.hydroscat.date_command()
        self.logger.info("DATE command")
        self.hydroscat.flourescence_command()
        self.logger.info("Fluorescence command")
        self.hydroscat.burst_command()
        self.logger.info("BURST command")
        self.change_state("START")


    def write_to_interface(self):
        if self.state == "START":
            self.hydroscat.start_command()
            self.logger.info("START command")
            self.change_state("RUNNING")
        elif self.state == "STOP":
            self.hydroscat.stop_command()
            self.logger.info("STOP command")
            self.change_state("IDLE")


    def close(self, wait_thread_join=True):
        if self.state == "RUNNING":
            self.change_state("STOP")
        super().close(wait_thread_join)


    def parse(self, packet):
        if self.state == "RUNNING":
            raw_packet = packet.decode()
            if raw_packet[0:2] in ["*T", "*D", "*H"]:
                data_dict = self.hydroscat.rawline2datadict(raw_packet)
                if raw_packet[0:2] != "*H":
                    return data_dict


    def handle_data(self, data, timestamp):
        # Update timeseries plot
        ts_data = [self.hydroscat.aux_data["Voltage"] if var_name == "Voltage" else data[var_name]
                   for var_name in self.widget_active_timeseries_variables_selected]
        if self.active_timeseries_variables_lock.acquire(timeout=0.125):
            try:
                self.signal.new_ts_data.emit(ts_data, timestamp)
            finally:
                self.active_timeseries_variables_lock.release()
        else:
            self.logger.error('Unable to acquire lock to update timeseries plot')

        # Update spectrum plot
        beta_vals = [data[name] for name in sorted(data) if name.startswith("bb")]
        self.signal.new_spectrum_data.emit([np.array(beta_vals)])

        # Format and signal aux data
        if self.hydroscat.aux_data["Time"] is not None:
            date_time = datetime.strftime(datetime.fromtimestamp(int(self.hydroscat.aux_data["Time"])),
                                          format="%Y-%m-%d %H:%M:%S")
            self.signal.new_aux_data.emit(['%.4f' % self.hydroscat.aux_data["Temperature"],
                                           '%.4f' % self.hydroscat.aux_data["Depth"],
                                           '%.4f' % self.hydroscat.aux_data["Voltage"],
                                           '%s' % date_time])

        # Log parsed data
        if self.log_prod_enabled and self._log_active:
            beta_vals = [value for key, value in data.items() if key.startswith("bb") or key.startswith("fl")]
            fields = [self.hydroscat.aux_data["Depth"],
                      self.hydroscat.aux_data["Voltage"]] + beta_vals
            self._log_prod.write(fields, timestamp)

            if not self.log_raw_enabled:
                self.signal.packet_logged.emit()


    def udpate_active_timeseries_variables(self, name, active):
        # ensure only one thread updates active timeseries variables
        if self.active_timeseries_variables_lock.acquire(timeout=0.25):
            try:
                self.active_variables[name] = active
                self.widget_active_timeseries_variables_selected = \
                    [name for name in self.active_variables if self.active_variables[name]]
            finally:
                self.active_timeseries_variables_lock.release()


class ProdLogger(Log):
    def __init__(self, header_lines, cfg, signal_new_file=None):
        super().__init__(cfg, signal_new_file)
        self.header_lines = header_lines


    def write_header(self):
        """Override to write calibration header lines before other header lines."""
        for line in self.header_lines:
            self._file.write("{}\n".format(line))

        super().write_header()
