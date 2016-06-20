# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-29 14:37:11
# @Last Modified by:   nils
# @Last Modified time: 2016-06-15 17:34:04

# from matplotlib import use as muse
# muse('Qt5Agg')
from matplotlib import pyplot as plt
import numpy as np

from threading import Thread
from time import sleep

class Plot():

    def __init__(self, _log):
        # Thread
        self.m_thread = None
        self.m_active = False

        # Parameters
        self.m_log = None

        # PlotWindow
        self.m_pw = None
        self.m_log = _log

    def Start(self):
        # Init window
        self.m_pw = PlotWindow()
        # Start thread
        self.m_thread = Thread(target=self.RunUpdate, args=())
        self.m_thread.daemon = True
        self.m_active = True
        self.m_bin_size = 0
        self.m_thread.start()


    def RunUpdate(self):
        print(self.m_log)
        while self.m_active:
            sleep(self.m_log.m_buffer_interval)
            # try:
            self.Update()
            # except:
                # print('Unexpected error while updating plot.')

    def Update(self):
        # Plot only first variable for now
        x = self.m_log.m_buffer['timestamp'].get()
        y = self.m_log.m_buffer[self.m_log.m_varnames[1]].get()
        self.m_pw.Update(x,y)

    def Stop(self, disp=True):
        # Stop thread
        if self.m_thread is not None:
            self.m_active = False
            if self.m_thread.isAlive():
                self.m_thread.join(self.m_log.m_buffer_interval * 1.1)
            elif disp:
                print('Plot thread already stopped.')
        elif disp:
            print('Plot thread not initialized.')
        # Delete window
        del(self.m_pw)

class PlotWindow():

    # Parameters
    m_fig = None
    m_ax = None
    m_hl = None

    def __init__(self, _limits=[0, 5]):
        plt.ion()
        # Set figure
        self.m_fig, self.m_ax = plt.subplots()
        self.m_hl, = plt.plot([], [])
        self.m_fig.show()
        # Set limits
        # self.m_ax.set_autoscaley_on(True)
        # self.m_ax.set_ylim(_limits[0], _limits[1])
        # Set
        self.m_ax.grid()

        # Display some information
        self.m_fig.canvas.set_window_title('Inlinino')
        self.m_ax.set_xlabel('Time')
        self.m_ax.set_ylabel('Signal')
        self.m_ax.set_title('Inlinino')

    def Update(self, _x, _y):
        # Update data
        self.m_hl.set_xdata(np.append(self.m_hl.get_xdata(), _x))
        self.m_hl.set_ydata(np.append(self.m_hl.get_ydata(), _y))
        # Update limits
        self.m_ax.relim()
        self.m_ax.autoscale_view()
        # Re Draw figure
        # plt.draw()
        # self.m_fig.canvas.manager.show()
        self.m_fig.canvas.draw()
        self.m_fig.canvas.flush_events()

    def __del__(self):
        plt.close(self.m_fig)

if __name__ == "__main__":
    p = Plot([0, 5])
    for x in np.arange(0, 40, 0.5):
        # print('Update ' + str(x))
        p.Update(x, np.sin(x)*2.5+2.5)
        sleep(0.01)