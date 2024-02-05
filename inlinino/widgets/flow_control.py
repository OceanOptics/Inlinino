from time import time

from inlinino.instruments.ontrak import Relay
from inlinino.widgets import GenericWidget


class FlowControlWidget(GenericWidget):

    def __init__(self, instrument):
        super().__init__(instrument)
        self.radio_instrument_control_filter.clicked.connect(self.set_switch_mode)
        self.radio_instrument_control_total.clicked.connect(self.set_switch_mode)
        self.radio_instrument_control_hourly.clicked.connect(self.set_switch_mode)
        self.radio_instrument_control_interval.clicked.connect(self.set_switch_mode)
        self.spinbox_instrument_control_filter_start_every.valueChanged.connect(self.set_switch_timing)
        self.spinbox_instrument_control_filter_duration.valueChanged.connect(self.set_switch_timing)

    def setup(self):
        if self.instrument.widget_flow_control_enabled:
            self.set_switch_mode()
            self.set_switch_timing()
            self.show()
        else:
            self.hide()

    def reset(self):
        self.setup()

    def set_switch_mode(self):
        if self.radio_instrument_control_filter.isChecked():
            self.instrument.relay.mode = Relay.ON
            self.group_box_instrument_control_filter_schedule.setEnabled(False)
        elif self.radio_instrument_control_total.isChecked():
            self.instrument.relay.mode = Relay.OFF
            self.group_box_instrument_control_filter_schedule.setEnabled(False)
        elif self.radio_instrument_control_hourly.isChecked():
            self.instrument.relay.mode = Relay.HOURLY
            self.group_box_instrument_control_filter_schedule.setEnabled(True)
            self.label_instrument_control_filter_start_every.setText('Start at minute')
            self.spinbox_instrument_control_filter_start_every.setValue(self.instrument.relay.hourly_start_at)
        elif self.radio_instrument_control_interval.isChecked():
            self.instrument.relay.interval_start = time() - self.instrument.relay.on_duration * 60
            self.instrument.relay.mode = Relay.INTERVAL
            self.group_box_instrument_control_filter_schedule.setEnabled(True)
            self.label_instrument_control_filter_start_every.setText('Every (min)')
            self.spinbox_instrument_control_filter_start_every.setValue(self.instrument.relay.off_duration)

    def set_switch_timing(self):
        if self.radio_instrument_control_hourly.isChecked():
            self.instrument.relay.hourly_start_at = self.spinbox_instrument_control_filter_start_every.value()
        elif self.radio_instrument_control_interval.isChecked():
            self.instrument.relay.off_duration = self.spinbox_instrument_control_filter_start_every.value()
        self.instrument.relay.on_duration = self.spinbox_instrument_control_filter_duration.value()
