Inlinino
========
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.8](https://img.shields.io/badge/Python-3.8-blue.svg)](https://www.python.org/downloads/)
[![Documentation Status](https://readthedocs.org/projects/inlinino/badge/?version=latest)](https://inlinino.readthedocs.io/en/latest/?badge=latest)

Inlinino is an open-source software data logger for oceanographers. It primarily log measurements from optical instruments deployed on research vessels during month long campaigns. Secondarily, it  provides real-time visualization, which helps users troubleshoot instruments in the field and ensure collection of quality data. Inlinino is designed to interface with either serial (RS-232) or analog instruments. The data received is logged in a timestamped raw format (as communicated by the instrument) or in a comma separated file (csv) for easy importation in data analysis software. Typically, a new log file is created every hour for simplicity of post-processing and easy backups. Instruments supported are: SeaBird TSG, Satlantic PAR, WET Labs ECO sensors (e.g. ECO-BB3, ECO-FLBBCD, ECO-BBFL2, ECO-3X1M, ECO-BB9, ECO-BBRT), WET Labs ACS, Sequoia LISST, and analog sensors through a data acquisition system (DataQ DI-1100 ). Other instruments can be added via the user interface if they output simple ascii data frame, otherwise the code is intended to be modular to support new instruments. 
     
The documentation of the project is available at [http://inlinino.readthedocs.io](http://inlinino.readthedocs.io/en/latest/).

Appropriate citation is:
Haentjens, N. and Boss, E., 2020. Inlinino: A Modular Software Data Logger for Oceanography. DIY Oceanography. DOI: [10.5670/oceanog.2020.112](https://doi.org/10.5670/oceanog.2020.112)


### Installation
Inlinino was bundled into a Windows executable and a macOS application. Both are available for download with a quick start guide in the [documentation](https://inlinino.readthedocs.io/en/latest/quick_start.html). Otherwise Inlinino can be installed from source using the setup.py file available on this repository, following the instructions below.

Download Inlinino code.
 
    wget https://github.com/OceanOptics/Inlinino/archive/master.zip
    unzip master.zip
    cd Inlinino-master
 
To install Inlinino (tested with python 3.8 only, should work with newer python versions):

    pip install -r requirements.txt

To use Ontrak ADU on Windows additional dll and python modules are needed. Note that in resources/ontrack the path to the dll need to be edited with `os.path.join(PATH_TO_RESOURCES, 'ontrak', 'AduHid')`.
    
    wget https://www.ontrak.net/images/adu_python_dll.zip
    unzip adu_python_dll.zip
    cp adu_python_dll/ontrak inlinino/ressources
    wget https://www.ontrak.net/images/adu_python_libusb.zip
    unzip adu_python_libusb.zip
    cp adu_python_libusb/libusb/* inlinino/ressources/libusb

Inlinino can then be started from the folder containing inlinino's source code with.

    python -m inlinino

### Inlinino Software
The application is written in Python 3, on top of pySerial, numpy, and PyQt5. The current version works with a "classic" Graphical User Interface. A web interface started to be implemented and can be found in the branch `tb-app` of this repository. A command line interface used to be available but was not ported to version >2.0.

The code is organized in:
  + `docs`: User Documentation ([ReadTheDocs](https://inlinino.readthedocs.io/))
  + `inlinino`: Inlinino source code
    - `instruments/`:  Instrument interfaces, more instrument types can be added there.
    - `ressources/`: User Interface Layout and Logo.
    - `*.py`: Core code of Inlinino.
    - `inlinino_cfg.json`: Applications parameters are saved in this file ([ReadTheDocs](https://inlinino.readthedocs.io/en/latest/cfg.html))
  + `mcu_firmwares`: Firmwares to upload on a microcontroller for the previous DAQ module (deprecated)
    - `PASC.cpp`: Precision analog to serial converter (PASC) firmware
    - `Simulino.cpp `: Instrument simulator to test Inlinino with microcontrollers simulating the behavior of scientific instruments.
  + `make.py`: Bundles Inlinino application into a .app or .exe depending on platform. pyInstaller must be installed.
  + `setup.py`: Python environment setup file.

When Inlinino is started an engineering log file is created in `logs/inlinino_<YYYYMMDD>_<hhmmss>.log` and keep track of most tasks executed (e.g. user interaction, creation of data log files, warnings, and potential errors).

### Questions and issues
For any questions or issues regarding Inlinino please contact [me](mailto:nils.haentjens+inlinino@maine.edu).
