from time import time

from inlinino.instruments.ontrak import RELAY_ON, RELAY_OFF, RELAY_HOURLY, RELAY_INTERVAL
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
        self.set_switch_mode()
        self.set_switch_timing()

    def reset(self):
        if self.instrument.widget_flow_control_enabled:
            self.setup()
            self.group_box_instrument_control.show()
        else:
            self.group_box_instrument_control.hide()

    def set_switch_mode(self):
        if self.radio_instrument_control_filter.isChecked():
            self.instrument.relay_status = RELAY_ON
            self.group_box_instrument_control_filter_schedule.setEnabled(False)
        elif self.radio_instrument_control_total.isChecked():
            self.instrument.relay_status = RELAY_OFF
            self.group_box_instrument_control_filter_schedule.setEnabled(False)
        elif self.radio_instrument_control_hourly.isChecked():
            self.instrument.relay_status = RELAY_HOURLY
            self.group_box_instrument_control_filter_schedule.setEnabled(True)
            self.label_instrument_control_filter_start_every.setText('Start at minute')
            self.spinbox_instrument_control_filter_start_every.setValue(self.instrument.relay_hourly_start_at)
        elif self.radio_instrument_control_interval.isChecked():
            self.instrument._relay_interval_start = time() - self.instrument.relay_on_duration * 60
            self.instrument.relay_status = RELAY_INTERVAL
            self.group_box_instrument_control_filter_schedule.setEnabled(True)
            self.label_instrument_control_filter_start_every.setText('Every (min)')
            self.spinbox_instrument_control_filter_start_every.setValue(self.instrument.relay_off_duration)

    def set_switch_timing(self):
        if self.radio_instrument_control_hourly.isChecked():
            self.instrument.relay_hourly_start_at = self.spinbox_instrument_control_filter_start_every.value()
        elif self.radio_instrument_control_interval.isChecked():
            self.instrument.relay_off_duration = self.spinbox_instrument_control_filter_start_every.value()
        self.instrument.relay_on_duration = self.spinbox_instrument_control_filter_duration.value()
