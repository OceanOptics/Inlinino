from inlinino.widgets import GenericWidget
from inlinino.instruments.ontrak import Relay


class PumpControlWidget(GenericWidget):
    def __init__(self, instrument, id=0):
        self.id = id
        super().__init__(instrument)
        self.group_box_pump_control.setTitle(f'Pump {self.id}')
        self.pb_toggle_pump.clicked.connect(self.toggle_pump)
        self.spinbox_pump_on.valueChanged.connect(self.set_timing)

    def setup(self):
        if self.instrument.widget_pump_controls_enabled[self.id]:
            self.instrument.relays[self.id].mode = Relay.HOURLY
            self.set_timing()
            self.show()
        else:
            self.hide()

    def reset(self):
        self.setup()

    def toggle_pump(self):
        if self.pb_toggle_pump.isChecked():
            self.pb_toggle_pump.setText('FORCE PUMP ON')
            self.instrument.relays[self.id].mode = Relay.ON
        else:
            self.pb_toggle_pump.setText('Force Pump On')
            self.instrument.relays[self.id].mode = Relay.HOURLY

    def set_timing(self):
        self.instrument.relays[self.id].hourly_start_at = 0
        self.instrument.relays[self.id].on_duration = self.spinbox_pump_on.value()
