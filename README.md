Inlinino
========
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.4](https://img.shields.io/badge/Python-3.4-blue.svg)](https://www.python.org/downloads/)
[![Python 3.5](https://img.shields.io/badge/Python-3.5-blue.svg)](https://www.python.org/downloads/)

_A modular software data logger for oceanography_


Inlinino is an open-source software data logger which main purpose is to log scientific measurements during extended periods at sea. It also provides real-time visualization, which helps users troubleshoot instruments in the field and prevents collection of bad data. Inlinino is designed to interface with either serial (RS-232) or analog instruments. Analog instruments are supported through a compatible data acquisition system, to date, the only one compatible is PASC (presented below). Serial instruments supported:
  + SeaBird TSG
  + Satlantic PAR
  + WETLabs ECO-Triples (e.g. ECO-BB3, ECO-FLBBCD, ECO-BBFL2, ECO-3X1M)
  + WETLabs ECO-BB9
  + WETLabs ECO-BBRT
  + WETLabs UBAT
  + WETLabs ACS: requires further testing before deployment (check branch acs-dev)
     
The documentation of the project is available at [http://inlinino.readthedocs.io](http://inlinino.readthedocs.io/en/latest/).

### Installation
Inlinino can be installed with a Windows installer ([instructions](https://inlinino.readthedocs.io/en/latest/quick_start.html)) or directly in your Python environment by following these instructions.

Download Inlinino code.
 
    wget https://github.com/OceanOptics/Inlinino/archive/master.zip
    unzip Inlinino-master.zip
    cd Inlinino-master
 
We recommend setting Inlinino in a virtual environment (e.g. miniconda). To set up a new python virtual environment with conda and install Inlinino:

    conda create --name Inlinino python=3
    source activate Inlinino
    python setup.py

Inlinino was tested with the following version of the python packages.
  + Python      3.4.4
  + numpy       1.9.3
  + pySerial    3.1.1
  + PyQt        4.11.4
  + PyQtGraph   0.9.10

The application is not compatible with PyQT 5. We are aware that the versions of these packages are not the most recent. You might have to install the packages manually starting with PyQT 4.11.4.

_Known bugs_:
  + Versions of pySerial <3.1.1 are not working properly with Inlinino on macOS.
  + PyQtGraph 0.9.10 was patched as follow to fix a known bug:
    + Replace line 171 of `pyqtgraph/graphicsItems/PlotItem/PlotItem.py` by:
    ```
    # axis = axisItems.get(k, AxisItem(orientation=k, parent=self))
    if k in axisItems.keys():
        axis = axisItems[k]
    else:
        axis = AxisItem(orientation=k, parent=self) 
    ```

Inlinino can then be started with the following commands.

    cd inlinino/
    python -o inlinino <path-to-cfg-file>

`<path-to-cfg-file>` must be replaced with the configuration file of your choice. Configuration files can be found in `inlinino/cfg`. `simulino_cfg.json` is a good choice to test the functionalities of the application as it provides instruments simulators. The complete documentation of Inlinino's configuration file is available on [ReadTheDocs](https://inlinino.readthedocs.io/en/latest/cfg.html). The python argument `-o` optimize the code and switch the flag `__debug__` to `False`. On Windows replace `python` by `pythonw` to mask the window command when starting the software. 

### Inlinino Software
The application is written in Python 3, on top of pySerial and numpy. Two user interfaces are available: a graphical user interface (GUI) based on PyQt 4 and PyQtGraph and a command-line interface (CLI). A web interface started to be implemented and can be found in the branch `tb-app` of this repository.

The code is organized in:
  + `docs`: Documentation presented on [ReadTheDocs](https://inlinino.readthedocs.io/)
  + `inlinino`: Inlinino source code
    - `cfg/`: Default location of configuration files used by Inlinino.
    - `instruments/`:  Instrument interfaces can be edited or added in this folder.
    - `ressources/`: The logo of Inlinino used for the Icon and the Splash screen is in this folder.
    - `*.py`: Core code of Inlinino.
  + `mcu_firmwares`: Firmwares to upload on a microcontroller
    - `PASC.cpp`: Precision analog to serial converter firmware
    - `Simulino.cpp `: Instrument simulator to test Inlinino with microcontrollers simulating the behavior of scientific instruments.

### PASC
_Precision Analog to Serial Converter_

The PASC is an optional data acquisition (DAQ) device. PASC is only required to log data from instruments communicating through analog channels. PASC can be built with an Arduino Uno type microcontroller and a precision analog to digital converter such as the Texas Instrument ADS1015 or ADS1115 [developpement boards](https://www.adafruit.com/product/1083). The wiring instructions to build your own are available at [Adafruit website](https://learn.adafruit.com/adafruit-4-channel-adc-breakouts/assembly-and-wiring).

We uploaded the firmware to the microcontroller following these instructions.
  1. Load mcu_firmwares/PASC.cpp in the [Arduino IDE[(<https://www.arduino.cc/en/main/software>):
        1. In ~/Documents/Arduino create a folder PASC/
        2. Copy and rename mcu_firmware/PASC.cpp to ~/Documents/Arduino/PASC/PASC.ino
        3. Load PASC.ino from Arduino Software (File > Open...)
  2. Comment/uncomment appropriate lines in PASC.ino following instructions in comments of the file.
  3. Compile and upload PASC to the microcontroller (button on the top left of Arduino IDE).

### Questions and issues
For any questions or issues regarding Inlinino please contact [me](mailto:nils.haentjens+inlinino@maine.edu).
