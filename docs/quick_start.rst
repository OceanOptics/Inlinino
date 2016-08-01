.. _quick-start:

===========
Quick Start
===========

This document will show you how to get up and running with Inlinino. You will have inlinino installed in 10 minutes and start logging data in 15 !

If you are already using python 3.x, go ahead to those `setup instructions <https://github.com/OceanOptics/Inlinino/blob/master/INSTALL.md>`__.

.. contents:: Table of Contents

.. _easy-install:

Easy installation
-----------------
The quick and easy installation is available on Windows only for now. If you are on OSX or Linux please go ahead to :ref:`the advance installation section <install>`.

Download
^^^^^^^^
Download the setup file for your operating system:

  + `Windows 32-bits <http://misclab.umeoce.maine.edu/inlinino/Inlinino_setup_win32.exe>`__
  + `Windows 64-bits <http://misclab.umeoce.maine.edu/inlinino/Inlinino_setup_win64.exe>`__

If you are logging data from analog instruments and therefor use an Arduino make sure the appropriate driver are installed. Instructions are available on `Arduino's website <https://www.arduino.cc/en/Guide/Windows>`__.

Install
^^^^^^^
Double click on the setup file you just downloaded and follow the instructions.

Quick configuration
-------------------
Let's just set up the instrument(s) you want to log data from.

  1. Create an empty text file in ``C:\Program Files\Inlinino\cfg\`` named "user_cfg.json".
  2. Copy the following empty instrument configuration in the file:

    ::

      {
        "instruments":{

        }
      }

  3. Pick one or mutiple instruments bellow and add there configuration to the configuration file you just created.

    + :ref:`WET Labs<cfg-wetlabs>` ECO-Triplet
    + :ref:`WET Labs<cfg-wetlabs>` ECO-BB9
    + :ref:`SBE TSG<cfg-sbe>`
    + :ref:`Simulator<cfg-embedded-simulino>` (for testing)

  4. Your configuration file will look like this if you choose to log data from a TSG and a BBFL2.

    ::

      {
        "instruments":{
          "TSG":{
            "module":"SBE",
            "name":"TSG",
            "variables":["T", "C", "S"],
            "units":["deg_C", "S/m", "no units"]
          },
          "BBFL2_200":{
            "module":"WETLabs",
            "name":"Triplet",
            "lambda":[660, 695, 460],
            "varname_header":["beta", "chl", "cdom"],
            "units":"counts"
          }
        }
      }

  5. Edit path to the user configuration file  you just created by editing line 16 of ``"C:\Program Files\Inlinino\__main__.py``.

    ::

      # Original line
      Inlinino(os.path.join(sys.path[0], 'cfg', 'simulino_cfg.json'))
      # User specific configuration
      Inlinino(os.path.join(sys.path[0], 'cfg', 'user_cfg.json'))


.. note::
  The user configuration file can have any name and can be located anywhere. By convention all Inlinino's configuration files are finishing by ``_cfg.json`` and are located in ``"C:\Program Files\Inlinino\cfg\"``.

Log your first data
-------------------
  1. Start Inlinino by double clicking on one of the Icon shortcut (on the Desktop or in the Start menu > Programs > Inlinino).
  If everything went well you will see a window similar to this:

  .. image:: screenshots/mw_global.png
    :scale: 50 %

  It can take up to 30 seconds for the interface to show up on slow computers.

  .. note::
    If nothing is showing up try to troubleshoot with indications available in :ref:`cfg-common-errors` section

  2. Connect instruments:

    a. Click on ``>`` button on the left of each instrument.
    b. The status of the instrument will switch to "active".
    c. Data will be plotted on the figure on right and displayed on the top left.

    .. note::
      More details about the instruments configuration and interface can be found in the :ref:`Configuration<cfg-instruments>` and :ref:`GUI<gui-instruments>` sections.

  3. Start logging data

    a. Click on ``Start`` button at the bottom left to start recording the data.
    b. By default data is recorded at 1 Hz and new log file are made hourly.

    .. note::
      More details about the logger configuration and interface can be found in the :ref:`Configuration<cfg-log>` and :ref:`GUI<gui-logger>` sections.

Next step
---------
The GUI is intuitive and very simple fill free to explore all the possibility by yourself, you cannot break anything. If you're not sure about a command, check the documentation.

Want to do more ? Look at the configuration files, few parameters can be adapted to your need there.

The instrument you would like to log data from is not available ? Add it ! There is an example on how to add the code required in the :ref:`cfg-add-custom-instrument` section.


.. Note::
  Any difficulties ? Ideas of improvements ? Let me know, I will be happy to discuss them with you.
  `Nils <mailto:nils.haentjens+inlinino@maine.edu>`__
