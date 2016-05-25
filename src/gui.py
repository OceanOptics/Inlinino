# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-14 16:55:47
# @Last Modified by:   nils
# @Last Modified time: 2016-05-22 20:38:28

import matplotlib.pyplot as plt
import matplotlib.animation as animation
import time

fig = plt.figure()
ax1 = fig.add_subplot(1, 1, 1)


def animate(i):
    pullData = open("sampleText.txt", "r").read()
    dataArray = pullData.split('\n')
    xar = []
    yar = []
    for eachLine in dataArray:
        if len(eachLine) > 1:
            x, y = eachLine.split(',')
            xar.append(int(x))
            yar.append(int(y))

    ax1.clear()
    ax1.plot(xar, yar)
ani = animation.FuncAnimation(fig, animate, interval=1000)
plt.show()
