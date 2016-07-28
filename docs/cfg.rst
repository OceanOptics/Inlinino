.. _cfg:

=============
Configuration
=============

The purpose of this section is to introduce users to the various settings available to tune Inlinino. It also explains how to add a variety of instruments to the interface in addition to plugin custom instruments.

All Inlinino's configuration is located in two json files:
  + inlinino/src/cfg/default_cfg.json
  + inlinino/src/cfg/<user_cfg>.json (user specific)

default_cfg.json should not be edited and is the first thing loaded when Inlinino starts. The path to the user specific configuration file should be specified as an argument when starting the application (More details in the `User configuration`_ section).

The configurations files contains 3 sections:
  - Application_
  - Log_
  - Instruments_

The two first are generally setup in default_cfg.json and are less susceptible to be ajusted. The instruments_ section is often the only section in <user_cfg.json>, in case any parameter from default_cfg.json needs to be modified in <user_cfg.json>, the entire section need to copied otherwise parameters will be missing and error will showup when starting Inlinino.

.. _cfg-application:

Application
===========
The main configuration of the application is done in the section ``app_cfg``.

``interface: "< gui | cli >"``
  The two options are:

    + gui: :ref:`gui`
    + cli: :ref:`cli`

  Most of the functionnality are available on both interface. The GUI is recommended for people that want to visualize data in real-time and do not have any ressources limitations (Inlinino usually run using 1-5 % of the CPU). The CLI is meant for use on servers without X or on computer with limited ressources.

  .. note::
    A web interface might come out in further realise in order to monitor data from ship network.

``theme: "< inside | outside >"``
  *Available only for the gui interface.*
  The two options are:

    + inside: the gui will be dark for a confortable use in lab or by night
    + outside: the gui will be bright for a confortable use outside in a sunny environment

``ui_update_frequency: <float>``
  *Available only for the gui interface.*
  Frequency (in Hertz) at which the user interface is refreshing. This value is only for updating the figure and the digital display on top left. It's not taken into account for logging purposes.

  A recommended value is one 1 which correspond to updating the gui every second.

  .. note::
    If your computer is going very slowly when Inlinino is running trying to decrease the value should make it more fluid.

``ui_disp_pos_shift: <int>``
  *Available only for the gui interface.*
  This parameter allow to shift the digital display of the instrument on the top of the side bar.

    + 1 would set the digital display just after the clock (see image bellow).

      .. image:: screenshots/sb_disp.png

    + 3 would set the digital display at the line below.

      .. image:: screenshots/sb_disp_3.png

  .. note::
    This feature is usefull especially when using instruments with 3. 6 or 9 channels such as the ECO-Triplet or the ECO-BB9 which allow to have one of them per line.

``verbosity: < int >``
  This parameters take an integer between 0 and 5
  0 corresponding to no informations relative to the application will be displayed
  5 corresponding to a high verbosisty of the application

  .. note::
    Deprecated parameter, this parameter will be removed in futur release of Inlinino.
    Consider using the argument ``-O`` while starting Inlinino instead.


Example of configuration for the :ref:`gui`: ::

  "app_cfg":{
    "verbosity":2,
    "interface":"gui",
    "theme":"outside",
    "ui_update_frequency":1,
    "ui_disp_pos_shift":1
  }

Example of configuration for the :ref:`cli`: ::

  "app_cfg":{
    "verbosity":2,
    "interface":"cli"
  }

.. _cfg-log:

Log
===
The log section of the configuration file concerns all the parameters of the logger, the core of Inlinino.

``frequency: < float >``
  Frequency (in Hertz) at which data is read from all the instruments and saved in the log file.

  If multiple instruments are running at different frequency the logger frequency should be set to the maximum frequency in order to record all the data.

  .. note ::
    If an instrument did not update its cache between two reading of the logger a `NaN` value will be kept at that time.

``interval_write: < float >``
  Interval at which data is written on the hard drive, a small interval will be hard for the hard drive whereas a too big interval might drive to a lost of more data in case of sudent power off of the computer.

  The interval units are ``1/frequency`` second(s). For example: ::

    frequency = 1
    interval_write = 60
    --> buffer is written every 60 seconds on the hard drive

  .. note::
    OSX seems to keep in a buffer the data up to when the file is closed, this result in lost of data in case of sudent power off of the computer. The maximum lost of data in case of unpredicted behaviours on OSX is determine by the length of the file. Windows is not affected by this issue.

``buffer_size: < float >``
  Size of the buffer (in seconds) to keep data in memory. This determine how much data will be plotted on the figure of the interface.

  The ``buffer_size`` needs to be striclty greater than ``interval_write``

  The ``buffer_size`` units are ``1/frequency`` second(s). For example: ::

    frequency = 1
    buffer_size = 120
    --> the figure of the GUI will display the last 2 minutes of data collected

  .. tip::
    If using Inlinino with the :ref:`cli` the best size for the ring buffer is: ``buffer_size = interval_write + 1``

  .. note::
    using a big ring buffer will make the application very slow as there will be more points to plot on the figure.

  .. note::
    Inlinino use a ring buffer in order to be able to run for weeks in a row.

``length: < float >``
  The length parameter caracterize how long the log files will be.
  The units are minutes.

  The length parameter should be : ``length >> interval_write``

``header: "< string >"``
  The header parameter indicate what should be the prefic of the log file name.
  This parameter can be modified (in the :ref:`GUI <gui-header>` or :ref:`CLI <cli-header>` ) when the application is running.

  .. note::
    Log file name follow this syntax ``<header>_YYYYMMDD_HHMMSS.csv``. For example a file with the header Inlinino created July 9, 2016 at 16:01:00 UTC would be named: ``Inlinino_20160709_160100.csv``.

``path: "< string >"``
  Path to where the log files will be saved.
  This parameter can be changed in the :ref:`GUI <gui-location>` when the application is running.

  .. note::
    On Windows, the path need to include two backslashes as they are special characters in JSON. For example: ``C:\\Data\\Inlinino"``.

Example of log configuration: ::

  "log":{
      "frequency":1,
      "interval_write":60,
      "buffer_size":120,
      "length":60,
      "header":"Inlinino",
      "path":"data"
    }

.. _cfg-instruments:

Instruments
===========

The following instruments are already implemented in Inlinino:

- `Analog`_ connection:

  * WET Labs WSCD: CDOM FLuorometer

- `Serial`_ connection:

  * SBE:

    - 45 Micro TSG: Thermosalinograph

  * WET Labs:

    - ECO-Triplet: 3 channels for backscatterers and/or fluorometers
    - ECO-BB9: 9 wavelength backscatterer

- `Simulators`_ (for testing purposes):

  * Random Gaussian Generator
  * Sinusoid with noise

Inlinino is not limited to those and is meant to log data from any kind of instruments for which a python API can be made. The `Adding a custom instrument`_ section is here to get started with that.

Any instrument is composed of the following parameters:

``instruments:{ < string > : {} }``
  The name of the instrument is in the instruments array and correspond to the name of a name-value set. The value of an instrument contains all its parameters.

  .. important::
    All the instrument in one instance of Inlinino must have unique names.

``module: "<string>"``
  The module parameter refers to which parent-class needs to be loaded to communicate with an instrument. It usually correspond to the brand of the instrument.
  Module available are:

    + Arduino
    + SBE
    + Simulino
    + WETLabs

``name: "<string>"``
  The name parameter refers to which child-class needs to be loaded to be able to communicate with the instrument. Usually it correspond to the name of the instrument.
  Name are specific to each module:

    - Arduino
      + ADS1015
      + Board
    - SBE
      + TSG
    - Simulino
      + Gauss
      + Sinus
    - WETLabs
      + BB9
      + Triplet

Other fields are present for most of the instruments:

``units: "< string >"``
  Units to display in the log file

``variables: {}``
  Variables is used to specify several variables with multiple parameters on one instrument.

``frequency: <int>``
  Frequency (in Hertz) at which the instrument is expected to run.

Example of instruments configuration: ::

  {
    "instruments":{
      "SimulinoRnd":{
        "module":"Simulino",
        "name":"Gauss",
        "...":"..."
      }
    }
  }

Availalble instruments
----------------------

In this section parameters specific to each instruments available are presented.

Analog
^^^^^^
In order to log data from an analog instrument you will need some additional hardware as you cannot plug them on most of the commercial computers.
Inlinino is able to communicate with an Arduino which will read the analog signal and send it to the computer. Depending on the precision required by the instrument we recommend the following configurations:

  + 10-bit signal: Arduino Uno
  + 12-bit signal: Arduino Uno + ADS1015
  + 16-bit signal: Arduino Uno + ADS1115

The Analog to Digital Converter (ADC) ADS1X15 also embbed a gain amplifier in order to reduice noise in small signal. More details on those ADC are available in there `documentation <https://cdn-learn.adafruit.com/downloads/pdf/adafruit-4-channel-adc-breakouts.pdf>`__.

.. note:
  Make sure that the driver for the Arduino are installed on the computer you plan to use. Instructions are available on Arduino's website:

    - `Windows <https://www.arduino.cc/en/Guide/Windows>`__
    - `Mac OS X <https://www.arduino.cc/en/Guide/MacOSX>`__
    - `Linux <https://www.arduino.cc/en/Guide/Linux>`__

.. note:
  Make sure the Arduino is flashed with the proper configuration of Inlinino for Arduino
    1. Load arduino/inlinino.cpp in the Arduino Software:

        1. in ~/Documents/Arduino create a folder Inlinino/
        2. copy and rename controlino.cpp to ~/Documents/Arduino/Inlinino/Inlinino.ino
        3. load Inlinino.ino from Arduino Software (File > Open...)

    2. Comment/uncomment appropriate lines following instructions at the beginning of the Inlinino.ino file (within Arduino IDE).

    3. Compile and upload Inlinino to the Arduino board (using the button on top left).


Arduino Uno + ADS1X15
  More documentation coming soon !

.. note:
  All Arduino models should be compatible with Inlinino but they have not been tested yet. If you encouter issues with a spcefic Arduino Model please contact us.

Serial
^^^^^^
More documentation coming soon !

Simulators
^^^^^^^^^^
More documentation coming soon !

Example of instrument configuration for simulated instruments: ::

  {
    "instruments":{
      "SimulinoRnd":{
        "module":"Simulino",
        "name":"Gauss",
        "frequency":1,
        "variables":{
          "rnd1":{
            "mu":2.5,
            "sigma":1,
            "seed":1,
            "units":"No Units"
          },
          "rnd2":{
            "mu":0.5,
            "sigma":0.2,
            "seed":2,
            "units":"No Units"
          }
        }
      },
      "SimulinoSin":{
        "module":"Simulino",
        "name":"Sinus",
        "frequency":1,
        "variables":{
          "sin":{
            "mu":2.5,
            "sigma":0,
            "seed":1,
            "start":0,
            "step":0.1,
            "units":"No Units"
          },
          "sin_noise":{
            "mu":1.0,
            "sigma":0.2,
            "seed":2,
            "start":1.57,
            "step":0.1,
            "units":"No Units"
          }
        }
      }
    }
  }

Adding a custom instrument
--------------------------
More documentation coming soon !

Arguments
=========
Some arguments are read by Inlinino when it is starting.

debug mode
----------
Inlinino use the default ``__debug__`` variable of python in order to switch between optimized and debug mode. The debug mode allow to display more information when the program is running in order to help while developping new features or debugging in case of unexcpected behaviour.

The global constant ``__debug__``  is true if Python was not started with an ``-O`` option (from `Python documentation <https://docs.python.org/2/library/constants.html>`_).

.. note::
  It's recommend to start the application with ``python -O __main__.py`` as the code will be optimized and therefor use less ressources.

.. note::
  If you installed the application through the Windows Installer (see :ref:`Quick Start <easy-install>`). `Inlinino` shortcut start the application with ``pythonw -O __main__.py`` whereas `Inlinino Debug`` start the application with ``python __main__.py`` which display a terminal window in addition to Inlinino where informations are displayed.

User configuration
------------------
The path to the user specific configuration file (<user_cfg.json>) should be passed in argument, for example: ::

  python -O __main__.py user_cfg.json

.. note::
  If you installed the application through the Windows Installer (see :ref:`Quick Start <easy-install>`). `Inlinino` shortcut start the application with ``pythonw -O __main__.py`` you can edit the shortcut properties (right click on the icon, choose properties) in order to setup your configuration file there, it would look like ``"C:\Program Files\Inlinino\WinPython-64bit-3.4.4.2\python-3.4.4.amd64\pythonw.exe" -O "C:\Program Files\Inlinino\__main__.py" "C:\Program Files\Inlinino\cfg\user_cfg.json"``

  .. image:: screenshots/win_shortcut_properties.png

Another way to modify path to the user configuration file is by editing line 16 of inlinino/src/__main__.py. ::

  # Original line
  Inlinino(os.path.join(sys.path[0], 'cfg', 'simulino_cfg.json'))
  # User specific line
  Inlinino(os.path.join(sys.path[0], 'cfg', 'user_cfg.json'))

.. note::
  If you installed the application through the Windows Installer (see :ref:`Quick Start <easy-install>`). The ``__main__.py`` file is located in ``C:\Program Files\Inlinino\__main__.py`` by default.

.. _cfg-common-errors:

Common errors
=============

Inlinino is very sensitive, it will not like any typo in the configuration files. Those will often lead to an application not starting or undesired effect.

Application does not start
  Start inlinino in debug mode and look at the error messages displayed, it will tell you what part of the configuration file it does not understand.

  If the error message is not helpfull, there is probably missing or extra: `{}`, `""`, or `,`.
