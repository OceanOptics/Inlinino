from inlinino.instruments.satlantic import Satlantic


class HyperNav(Satlantic):
    def __init__(self, uuid, signal, *args, **kwargs):
        super().__init__(uuid, signal, *args, **kwargs)
        self.plugin_metadata_enabled = False  # TODO include in hypernav_cal module
        self.plugin_hypernav_cal_enabled = True
