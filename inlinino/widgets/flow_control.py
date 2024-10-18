from time import time

from inlinino.instruments.ontrak import Relay
from inlinino.widgets import GenericWidget


class FlowControlWidget(GenericWidget):

    def __init__(self, instrument, id=0):
        self.id = id
        super().__init__(instrument)
        self.group_box_instrument_control.setTitle(f'Switch {self.id}')
        self.radio_instrument_control_filter.clicked.connect(self.set_switch_mode)
        self.radio_instrument_control_total.clicked.connect(self.set_switch_mode)
        self.radio_instrument_control_hourly.clicked.connect(self.set_switch_mode)
        self.radio_instrument_control_interval.clicked.connect(self.set_switch_mode)
        self.spinbox_instrument_control_filter_start_every.valueChanged.connect(self.set_switch_timing)
        self.spinbox_instrument_control_filter_duration.valueChanged.connect(self.set_switch_timing)

    def setup(self):
        if self.instrument.widget_flow_controls_enabled[self.id]:
            self.set_switch_mode()
            self.set_switch_timing()
            self.show()
        else:
            self.hide()

    def reset(self):
        self.setup()

    def set_switch_mode(self):
        if self.radio_instrument_control_filter.isChecked():
            self.instrument.relays[self.id].mode = Relay.ON
            self.group_box_instrument_control_filter_schedule.setEnabled(False)
        elif self.radio_instrument_control_total.isChecked():
            self.instrument.relays[self.id].mode = Relay.OFF
            self.group_box_instrument_control_filter_schedule.setEnabled(False)
        elif self.radio_instrument_control_hourly.isChecked():
            self.instrument.relays[self.id].mode = Relay.HOURLY
            self.group_box_instrument_control_filter_schedule.setEnabled(True)
            self.label_instrument_control_filter_start_every.setText('Start at minute')
            self.spinbox_instrument_control_filter_start_every.setValue(self.instrument.relays[self.id].hourly_start_at)
        elif self.radio_instrument_control_interval.isChecked():
            self.instrument.relays[self.id].interval_start = time() - self.instrument.relays[self.id].on_duration * 60
            self.instrument.relays[self.id].mode = Relay.INTERVAL
            self.group_box_instrument_control_filter_schedule.setEnabled(True)
            self.label_instrument_control_filter_start_every.setText('Every (min)')
            self.spinbox_instrument_control_filter_start_every.setValue(self.instrument.relays[self.id].off_duration)

    def set_switch_timing(self):
        if self.radio_instrument_control_hourly.isChecked():
            self.instrument.relays[self.id].hourly_start_at = self.spinbox_instrument_control_filter_start_every.value()
        elif self.radio_instrument_control_interval.isChecked():
            self.instrument.relays[self.id].off_duration = self.spinbox_instrument_control_filter_start_every.value()
        self.instrument.relays[self.id].on_duration = self.spinbox_instrument_control_filter_duration.value()
