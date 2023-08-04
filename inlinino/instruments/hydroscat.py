from inlinino.instruments import Instrument

import aquasense.hydroscat

from datetime import datetime

from inlinino.instruments import InterfaceException

import io

import threading
from time import time, sleep

class HydroScat(Instrument):

    REQUIRED_CFG_FIELDS = ['calibration_file', 'model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'fluorescence',
                           'start_delay', 'warmup_time',
                           'burst_duration', 'burst_cycle',
                           'total_duration', 'log_period',
                           'variable_names', 'variable_units', 'variable_precision']

    def __init__(self, uuid, signal, *args, **kwargs):
        super().__init__(uuid, signal, *args, **kwargs)

        # Default serial communication parameters
        self.default_serial_baudrate = 9600
        self.default_serial_timeout = 1

        # Auxiliary Data Plugin
        self.widget_aux_data_enabled = True
        self.widget_aux_data_variable_names = ['Temp. (ºC)', 'Depth (m)', 'Time']

        # Device command state machine
        self.state = "IDLE"


    def setup(self, cfg):
        source = io.TextIOWrapper(io.BufferedRWPair(self._interface._serial,
                                                    self._interface._serial))

        # TODO: fix out, serial_mode, num_channels (need a setup UI widget)
        # TODO: instead of verbose, could pass a logger object
        # TODO: is burst mode used?
        self.hydroscat = aquasense.hydroscat.HydroScat(
                            cal_path=cfg["calibration_file"], source=source,
                            out=None, sep=None, num_channels=8, serial_mode=False,
                            fluorescence_control=cfg["fluorescence"],
                            start_delay=cfg["start_delay"],
                            warmup_time=cfg["warmup_time"],
                            burst_duration=cfg["burst_duration"],
                            burst_cycle=cfg["burst_cycle"],
                            total_duration=cfg["total_duration"],
                            log_period=cfg["log_period"],
                            verbose=True)
        
        # Overload cfg with HydroScat specific parameters
        cfg['variable_names'] = self.hydroscat.channel_names()
        cfg['variable_units'] = ['beta' for n in range(1, len(cfg['variable_names'])+1)]
        cfg['variable_precision'] = ['%.9f' for n in range(1, len(cfg['variable_names'])+1)]
        cfg['terminator'] = b'\r\n'

        # Set standard configuration and check cfg input
        super().setup(cfg)
        self.logger.info("setup !!")


    def init_interface(self):
        self.hydroscat.date_command()
        self.logger.info("DATE command !!")
        self.hydroscat.flourescence_command()
        self.logger.info("Flourescence command !!")
        self.hydroscat.burst_command()
        self.logger.info("BURST command !!")

    # State machine: IDLE => START => RUNNING => STOP => IDLE => START => RUNNING ...

    def write_to_interface(self):
        if self.state == "START":
            self.hydroscat.start_command()
            self.logger.info("START command !!")
            self.state = "RUNNING"
        elif self.state == "STOP":
            self.hydroscat.stop_command()
            self.logger.info("STOP command !!")
            self.state = "IDLE"


    def log_start(self):
        if self.state == "IDLE":
            self.state = "START"
        super().log_start()

    def log_stop(self):
        if self.state == "RUNNING":
            self.state = "STOP"
        super().log_stop()

    def close(self, *args, **kwargs):
        if self.alive:
            self.hydroscat.stop_command()
            self.state = "IDLE"
            sleep(self._interface.timeout)
        super().close(*args, **kwargs)


    def parse(self, packet):
        data = [None] * len(self.variable_names)
        if self.state == "RUNNING":
            raw_packet = packet.decode()
            self.logger.info("{} !!".format(raw_packet))
            if raw_packet[0:2] in ["*T", "*D", "*H"]:
                self.logger.info("data packet")
                data_dict = self.hydroscat.rawline2datadict(raw_packet)
                if raw_packet[0:2] != "*H":
                    data = [n for n in data_dict.values()][2:]

        return data


    def handle_data(self, data, timestamp):
        super().handle_data(data, timestamp)
        self.logger.info("handle_data !!")
        # Format and signal aux data
        # TODO: instead, allfields(not None)
        if self.hydroscat.aux_data["Time"] is not None:
            # TODO: fix old formats!
            date_time = datetime.strftime(datetime.fromtimestamp(int(self.hydroscat.aux_data["Time"])), format="%m/%d/%Y %H:%M:%S")
            self.signal.new_aux_data.emit(['%.4f' % self.hydroscat.aux_data["Temperature"],
                                           '%.4f' % self.hydroscat.aux_data["Depth"],
                                           '%s' % date_time])
            self.logger.info("aux data !!")
