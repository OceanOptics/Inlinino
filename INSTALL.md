Install Inlinino
================

This document intend to explains how to setup Inlinino to people familiar to the python environment. If you are not familiar to python, an easy installation procedure for Windows is describbed on the [documentation of the project](http://inlinino.readthedocs.io/en/latest/quick_start.html).

## Installing Inlinino
Inlinino is written in python 3.x, so it runs on Windows, OSX and Linux.

The first step is to install python 3.x:
Download python 3.4 or latest on the [python.org website](https://www.python.org/downloads/). Please be sure to download the appropriate version for you computer, note that the code is not compatible with python 2.7.
Start the installation procedure and leave everything by default *except* if running Windows, at the Customize Python 3.4.X (64-bit) step: select `Add python.exe to Path` to install it on the disk.

Install the python package necessary to run Inlinino (if use virtualenv replace pip by the appropriate command, ex: conda):
```
pip install pyserial numpy
```
Additional packages are used by the user interface (UI), if you intend to use both UI install all the packages bellow.
- Graphical User Interface (GUI): requires PyQt and PyQtGraph
```
pip install pyqt
```
PyQtGraph is available at [http://www.pyqtgraph.org](http://www.pyqtgraph.org), please select the appropriate version for your OS. On windows follow the steps of the installer. On OSX or Linux just decompress the archive and run `python setup.py install`.

The current code was tested with:
Requirements:
- Python      3.4.4
- numpy       1.9.3
- pySerial    3.1.1
- PyQt        4.11.4
- PyQtGraph   0.9.1
Bugs have been found with earlier release of pySerial on OSX.

## Installing Inlinino for Arduino
If you plan to log data from an analog instrument you will need an Arduino and you will need to flash it following those steps.

Inlinino Arduino Controller is written in C++ and design to run on any Arduino device (only Arduino Uno has been tested to date).

The simplest way to install it is to use Arduino Software. Steps-by-steps instructions for setting up the Arduino Software (IDE) on your computer and connecting it to an Arduino board are available for your OS following those links:
- [Windows](https://www.arduino.cc/en/Guide/Windows)
- [Mac OS X](https://www.arduino.cc/en/Guide/MacOSX)
- [Linux](https://www.arduino.cc/en/Guide/Linux)

Load arduino/inlinino.cpp in the Arduino Software:
- in ~/Documents/Arduino create a folder Inlinino/
- copy and rename controlino.cpp
  to ~/Documents/Arduino/Inlinino/Inlinino.ino
- load Inlinino.ino from Arduino Software (File > Open...)

Comment/uncomment appropriate lines following instructions
at the beginning of the file.

Compile and upload Inlinino to the Arduino board (using the button on top left).
