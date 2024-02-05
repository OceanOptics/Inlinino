from inlinino.widgets import GenericWidget
from inlinino.instruments.ontrak import Relay


class PumpControlWidget(GenericWidget):
    def __init__(self, instrument):
        super().__init__(instrument)
        self.pb_toggle_pump.clicked.connect(self.toggle_pump)
        self.spinbox_pump_on.valueChanged.connect(self.set_timing)

    def setup(self):
        if self.instrument.widget_pump_control_enabled:
            self.instrument.relay.mode = Relay.HOURLY
            self.set_timing()
            self.show()
        else:
            self.hide()

    def reset(self):
        self.setup()

    def toggle_pump(self):
        if self.pb_toggle_pump.isChecked():
            self.pb_toggle_pump.setText('FORCE PUMP ON')
            self.instrument.relay.mode = Relay.ON
        else:
            self.pb_toggle_pump.setText('Force Pump On')
            self.instrument.relay.mode = Relay.HOURLY

    def set_timing(self):
        self.instrument.relay.hourly_start_at = 0
        self.instrument.relay.on_duration = self.spinbox_pump_on.value()
