from inlinino.widgets import GenericWidget
from inlinino.instruments.ontrak import RELAY_ON, RELAY_HOURLY


class PumpControlWidget(GenericWidget):
    def __init__(self, instrument):
        super().__init__(instrument)
        self.pb_toggle_pump.clicked.connect(self.toggle_pump)
        self.spinbox_pump_on.valueChanged.connect(self.set_timing)

    def setup(self):
        self.instrument.relay_status = RELAY_HOURLY
        self.set_timing()

    def reset(self):
        if self.instrument.widget_pump_control_enabled:
            self.setup()
            self.group_box_pump_control.show()
        else:
            self.group_box_pump_control.hide()

    def toggle_pump(self):
        if self.pb_toggle_pump.isChecked():
            self.pb_toggle_pump.setText('FORCE PUMP ON')
            self.instrument.relay_status = RELAY_ON
        else:
            self.pb_toggle_pump.setText('Force Pump On')
            self.instrument.relay_status = RELAY_HOURLY

    def set_timing(self):
        self.instrument.relay_hourly_start_at = 0
        self.instrument.relay_on_duration = self.spinbox_pump_on.value()
