from inlinino.instruments import Instrument

import aquasense.hydroscat

from datetime import datetime

import io
import numpy as np

from threading import Lock
from time import sleep


class HydroScat(Instrument):

    REQUIRED_CFG_FIELDS = ['calibration_file', 'model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'burst_mode',
                           'sleep_on_memory_full',
                           'fluorescence',
                           'start_delay', 'warmup_time',
                           'burst_duration', 'burst_cycle',
                           'total_duration', 'log_period',
                           'variable_names', 'variable_units', 'variable_precision']

    def __init__(self, uuid, signal, *args, **kwargs):
        # Instrument state machine
        self.state = "IDLE"
        self.previous_state = None

        super().__init__(uuid, signal, *args, **kwargs)

        self.all_data = []

        # Default serial communication parameters
        self.default_serial_baudrate = 9600
        self.default_serial_timeout = 1

        # Auxiliary Data Plugin
        self.widget_aux_data_enabled = True
        self.widget_aux_data_variable_names = ['Temp. (ºC)', 'Depth (m)', 'Voltage (V)', 'Time']

        # Init Channels to Plot widget
        self.widget_select_channel_enabled = True
        self.active_timeseries_variables_lock = Lock()

        # Init Spectrum Plot widget
        self.spectrum_plot_enabled = True
        self.spectrum_plot_axis_labels = dict(y_label_name='Backscattering',
                                              y_label_units='beta')
        # self.spectrum_plot_trace_names = [["bb420", "bb550", "bb442", "bb676", "bb488",
        #                                   "bb852", "fl550", "fl676"]]
        self.spectrum_plot_trace_names = ["beta"]
        #self.spectrum_plot_x_values = [[0 for name in self.spectrum_plot_trace_names][2:]]
        #self.spectrum_plot_x_values = [np.array([420,550,442,676,488,852,550,676])]
        #self.spectrum_plot_x_values = [np.array([420,442,488,550,550,676,676,852])]
        self.spectrum_plot_x_values = [np.array([420,442,488,550,676,852])]



    def setup(self, cfg):
        source = io.TextIOWrapper(io.BufferedRWPair(self._interface._serial,
                                                    self._interface._serial))
        # TODO: fix out, serial_mode ?
        # TODO: num_channels (setup UI widget or needed? => can't we just get this from .cal file?)
        # TODO: instead of verbose, could pass a logger object
        self.hydroscat = aquasense.hydroscat.HydroScat(
                            cal_path=cfg["calibration_file"], source=source,
                            out=None, sep=",", num_channels=8, serial_mode=False,
                            burst_mode=cfg["burst_mode"],
                            sleep_on_memory_full=cfg["sleep_on_memory_full"],
                            fluorescence_control=cfg["fluorescence"],
                            start_delay=cfg["start_delay"],
                            warmup_time=cfg["warmup_time"],
                            burst_duration=cfg["burst_duration"],
                            burst_cycle=cfg["burst_cycle"],
                            total_duration=cfg["total_duration"],
                            log_period=cfg["log_period"],
                            verbose=True)

        # Overload cfg with HydroScat specific parameters
        cfg['variable_names'] = ["Depth", "Voltage"] + self.hydroscat.channel_names()
        cfg['variable_units'] = ["m", "V"] + ['beta' for n in range(3, len(cfg['variable_names'])+1)]
        # cfg['variable_names'] = self.hydroscat.channel_names()
        # cfg['variable_units'] = ['beta' for n in range(3, len(cfg['variable_names'])+1)]
        cfg['variable_precision'] = ['%.3f', '%.3f'] + ['%.9f' for n in range(3, len(cfg['variable_names'])+1)]
        # cfg['variable_precision'] = ['%.9f' for n in range(3, len(cfg['variable_names'])+1)]
        cfg['terminator'] = b'\r\n'

        # Active Timeseries Variables
        self.active_variables = {var_name:True for var_name in cfg['variable_names']}
        self.active_variables["Depth"] = False
        self.active_variables["Voltage"] = False
        self.widget_active_timeseries_variables_names = cfg['variable_names']
        self.widget_active_timeseries_variables_selected = \
                    [name for name in self.active_variables if self.active_variables[name]]
        
        # Update wavelengths for Spectrum Plot
        # (plot is updated after the initial instrument setup or button click)
        self.spectrum_plot_trace_names = cfg['variable_names'][2:]
        betawavs = [int(betalab[2:]) for betalab in cfg['variable_names'][2:]]
        self.spectrum_plot_x_values = [np.array(betawavs)]

        # If we're not in the idle state (i.e. RUNNING or STOPPED)
        if self.previous_state != "IDLE":
            try:
                self.close()
                self.change_state("IDLE")
            except:
                pass

        # Set standard configuration and check cfg input
        super().setup(cfg)
        self.logger.info("setup")

    def change_state(self, state):
        self.previous_state = self.state
        self.state = state
        self.logger.info("{} -> {}".format(self.previous_state, state))


    def init_interface(self):
        # invoked after channel open request (via Open button)
        self.init()


    def init(self):
        self.hydroscat.date_command()
        self.logger.info("DATE command")
        self.hydroscat.flourescence_command()
        self.logger.info("Fluorescence command")
        self.hydroscat.burst_command()
        self.logger.info("BURST command")
        self.change_state("READY")

    # State machine: start_state =>
    #                IDLE =open button=> READY =start button=> START =/start command=>
    #                RUNNING =stop button=> STOP =/stop command=> READY =close button=>
    #                IDLE => ...

    def write_to_interface(self):
        # TODO: may need to make this a monitor
        if self.state == "START":
            self.hydroscat.start_command()
            self.logger.info("START command")
            self.change_state("RUNNING")
        elif self.state == "STOP":
            self.hydroscat.stop_command()
            self.logger.info("STOP command")
            self.change_state("READY")


    def log_start(self):
        if self.state == "READY":
            self.change_state("START")
        super().log_start()


    def log_stop(self):
        if self.state == "RUNNING":
            self.change_state("STOP")
        super().log_stop()


    def open(self, **kwargs):
        super().open(**kwargs)
        if self.alive:
            while self.state != "READY":
                sleep(0.1)


    # def close(self, wait_thread_join=True):
    #     if self.alive:
    #         self.hydroscat.stop_command()
    #         self.logger.info("STOP command")
    #         self.change_state("IDLE")
    #     super().close(wait_thread_join)


    def parse(self, packet):
        data = [None] * len(self.widget_active_timeseries_variables_selected)
        if self.state == "RUNNING":
            raw_packet = packet.decode()
            self.logger.info("{}".format(raw_packet))
            if raw_packet[0:2] in ["*T", "*D", "*H"]:
                self.logger.info("data packet")
                data_dict = self.hydroscat.rawline2datadict(raw_packet)
                if raw_packet[0:2] != "*H":
                    # get all selected values
                    # ensure only one thread updates active timeseries variables
                    if self.active_timeseries_variables_lock.acquire(timeout=0.25):
                        try:
                            data = []
                            for var_name in self.widget_active_timeseries_variables_selected:
                                if var_name == "Voltage":
                                    data.append(self.hydroscat.aux_data[var_name])
                                else:
                                    data.append(data_dict[var_name])
                        finally:
                            self.active_timeseries_variables_lock.release()
                    else:
                        self.logger.error('Unable to acquire lock to update active timeseries variables')

                    # also, get all values
                    self.all_data = [data_dict[key] for key in data_dict]

        return data


    def handle_data(self, data, timestamp):
        if all([datum is not None for datum in data]):
            # Update timeseries plot
            if self.active_timeseries_variables_lock.acquire(timeout=0.125):
                try:
                    self.signal.new_ts_data.emit(data, timestamp)
                finally:
                    self.active_timeseries_variables_lock.release()
            else:
                self.logger.error('Unable to acquire lock to update timeseries plot')

            # Update spectrum plot
            self.signal.new_spectrum_data.emit([np.array(self.all_data[2:8])])

            # Format and signal aux data
            if self.hydroscat.aux_data["Time"] is not None:
                # TODO: fix old formats!
                date_time = datetime.strftime(datetime.fromtimestamp(int(self.hydroscat.aux_data["Time"])), format="%m/%d/%Y %H:%M:%S")
                self.signal.new_aux_data.emit(['%.4f' % self.hydroscat.aux_data["Temperature"],
                                               '%.4f' % self.hydroscat.aux_data["Depth"],
                                               '%.4f' % self.hydroscat.aux_data["Voltage"],
                                               '%s' % date_time])
                self.logger.info("aux data")

            # Log parsed data
            if self.log_prod_enabled and self._log_active:
                fields = [self.hydroscat.aux_data["Depth"],
                          self.hydroscat.aux_data["Voltage"]] + self.all_data
                #self._log_prod.write(self.hydroscat.sep.join([str(field) for field in fields]), timestamp)
                self._log_prod.write(fields, timestamp)

                if not self.log_raw_enabled:
                    self.signal.packet_logged.emit()

    # TODO: wrong spelling of update
    def udpate_active_timeseries_variables(self, name, active):
        # ensure only one thread updates active timeseries variables
        if self.active_timeseries_variables_lock.acquire(timeout=0.25):
            try:
                self.active_variables[name] = active
                self.widget_active_timeseries_variables_selected = \
                    [name for name in self.active_variables if self.active_variables[name]]
            finally:
                self.active_timeseries_variables_lock.release()
