Welcome to Inlinino
===================

Inlinino is an open-source software data logger for oceanographers. It primarily log measurements from optical instruments deployed on research vessels during month long campaigns. Secondarily, it  provides real-time visualization, which helps users troubleshoot instruments in the field and ensure collection of quality data. Inlinino is designed to interface with either serial (RS-232) or analog instruments. The data received is logged in a timestamped raw format (as communicated by the instrument) or in a comma separated file (csv) for easy importation in data analysis software. Typically, a new log file is created every hour for simplicity of post-processing and easy backups. Instruments supported are: SeaBird TSG, Satlantic PAR, WET Labs ECO sensors (e.g. ECO-BB3, ECO-FLBBCD, ECO-BBFL2, ECO-3X1M, ECO-BB9, ECO-BBRT), WET Labs ACS, Sequoia LISST, and analog sensors through a data acquisition system (DataQ DI-1100 ). Other instruments can be added via the user interface if they output simple ascii data frame, otherwise the code is intended to be modular to support new instruments. The use and validation of the software are documented in Haëntjens and Boss 2020 (`DIY Oceanography <https://doi.org/10.5670/oceanog.2020.112>`_).

.. note::
      OUTDATED DOCUMENTATION! PASC is deprecated and replaced by DataQ or ADU data acquisition hardware (DAQ). Several new instruments are supported including HyperBB, HyperNAV, HyperOCR, Suna and more. Nonetheless, the user experience is very similar and current documentation still applies to most features.

.. image:: screenshots/main_window_acs.png
  :scale: 35 %
  :align: center

Index
^^^^^
.. toctree::
   :maxdepth: 2

    Quick Start<quick_start>
    Configuration<cfg>
    Precision Analog to Serial Converter (PASC)<pasc>
