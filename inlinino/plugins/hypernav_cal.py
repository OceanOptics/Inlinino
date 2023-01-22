from inlinino.plugins import GenericPlugin


class HyperNavCalPlugin(GenericPlugin):

    def __init__(self, instrument):
        super().__init__(instrument)

    def show(self):
        self.group_box_instrument_control.show()
        super().show()

    def hide(self):
        self.group_box_instrument_control.hide()
        super().hide()

    def setup(self):
        self.set_switch_mode()
        self.set_switch_timing()
