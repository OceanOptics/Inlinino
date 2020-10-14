.. _cfg:

=============
Configuration
=============

Essential settings are explained in the :ref:`Quick Start <quick-start>` Section. More advanced settings are detailed below. All parameters editable through Inlinino's user interface are saved in the inlinino_cfg.json file. This file is located in Inlinino's root directory on Windows and under Inlinino-v\ |release|.app/Contents/Resources/inlinino_cfg.json on macOS. The configuration file follows json syntax. The section `instruments` contains an array with the settings of each instruments configured to date. Some parameters are :ref:`common <common-parameters>` to every instrument type while others are :ref:`specific <specific-parameters>` to each instrument. :ref:`Example of configuration<example-cfg>` for each instrument type are listed at the end of the chapter.

.. warning::
   Be careful when manually editing the configuration file. Breaking the json syntax might prevent Inlinino from starting. It's recommended to backup the configuration file before making any modifications.

.. contents:: Table of Contents

.. _common-parameters:

Common parameters
=================
List of parameters common and required by every instrument type.

``module: <string>``
      The module parameter refers to which parent-class needs to be loaded to communicate with an instrument. The   modules/types of instrument implemented are:

        + generic: Class used for most instruments outputting simple ascii frames.
        + dataq: Specific to the DataQ DI-1100 data acquisition module to log analog instruments
        + lisst: Specific to Sequoia LISST instrument
        + acs: Specific to WET Labs AC-S and AC-9 instruments

``manufacturer: <string>``
    Instrument manufacturer. This field can only contain the following characters: A-Z, a-z, 0-9.

``model: <string>``
    Instrument model. This field can only contain the following characters: A-Z, a-z, 0-9.

``serial_number: <string>``
    Instrument serial number. This field can only contain the following characters: A-Z, a-z, 0-9.

``log_path: <string>``
    Path to the directory in which the data from the instruments is logged.

    .. note::
        On Windows, the path need to include two backslashes as they are special characters in JSON. For example: ``C:\\Data\\Inlinino``.

``log_raw: <boolean>``
    Indicate if log the raw data coming from an instrument.

    .. note::
        For the ACS this option logs the binary data received from the instrument. It is highly recommended to set it to `True`, as it allows to reprocess the raw data in case of parsing issues with Inlinino. By defaults it is enabled when using the user interface.

``log_products: <boolean>``
    Indicate to log data received in a comma separated value file, easily read by data analysis software.

    .. note::
        For the ACS on long cruises (e.g. month, year), one might want to desable this parameter as the volume of data collected is significantly higher when enabled


.. _specific-parameters:

Specific Parameters
===================
List of parameters specific to an instrument type/module.

Generic Instruments
"""""""""""""""""""
``terminator: <dict>``
    Indicate the end of the frame, hence the beginning of the next frame. For example:

    .. code-block:: json

        {"terminator": {
          "__bytes__": "ascii",
          "content": "\r\n"
        }}

``separator: <dict>``
    Element separating values in frame. For example:

    .. code-block:: json

        {"separator": {
          "__bytes__": "ascii",
          "content": "\t"
        }}

``variable_names: <list>``
    List of variable names separated by commas.

``variable_units: <list>``
    List of variable units separated by commas.

``variable_columns: <list>``
    List of position of each variable in the frame.

``variable_types: <list>``
    List of type of each variable. Can either be a floating number (`float`) or an integer (`int`).

``variable_precision: <list>``
    List of string format used for each variables to write product log file. Typically `%d` for integers and `%.3f` for floating number with a precision of 3 decimal places.

.. note::
    All list must have the same number of elements.

Analog Instruments
""""""""""""""""""
``channels_enabled: < list >``
    List of analog channels to log data from.

    .. code-block:: json

        {"channels_enabled": [1,2]}

Sequoia LISST
"""""""""""""
``device_file: < string >``
    Path to device file, also referred as instrument file, from the manufacturer.

    .. code-block:: json

        {"device_file": "cfg/LISST1183_20180119_InstrumentData.txt"}

``ini_file: < string >``
    Path to initialization file (.ini) from the manufacturer.

    .. code-block:: json

        {"ini_file": "cfg/LISST1183_20180119_Lisst.ini"}

WET Labs ACS
""""""""""""
``device_file: < string >``
    Path to device file from the manufacturer.

    .. code-block:: json

        {"device_file": "cfg/acs301_20180129.dev"}


.. _example-cfg:

Example of configurations
=========================

Generic Instruments
"""""""""""""""""""
Example of configuration for a WET Labs ECO-BB3.

.. code-block:: json

    {
      "manufacturer": "WetLabs",
      "model": "BB3",
      "serial_number": "349",
      "module": "generic",
      "terminator": {
        "__bytes__": "ascii",
        "content": "\r\n"
      },
      "separator": {
        "__bytes__": "ascii",
        "content": "\t"
      },
      "variable_names": ["beta470", "beta532", "beta660"],
      "variable_units": ["counts", "counts", "counts"],
      "variable_columns": [3, 5, 7],
      "variable_types": ["int", "int", "int"],
      "variable_precision": ["%d", "%d", "%d"],
      "variable_displayed": ["beta470", "beta532", "beta660"],
      "log_raw": false,
      "log_products": true,
      "log_path": "data"
    }


Analog Instruments
""""""""""""""""""
Example of configuration for a DataQ DI-1100.

.. code-block:: json

    {
      "module": "dataq",
      "manufacturer": "WetLabs",
      "model": "WSCD",
      "serial_number": "859",
      "log_path": "data",
      "log_raw": false,
      "log_products": true,
      "channels_enabled": [2]
    }


Sequoia LISST
"""""""""""""
Example of configuration for a Sequoia LISST.

.. code-block:: json

    {
      "manufacturer": "Sequoia",
      "model": "LISST",
      "serial_number": "1183",
      "module": "lisst",
      "ini_file": "cfg/LISST1183_20180119_Lisst.ini",
      "device_file": "cfg/LISST1183_20180119_InstrumentData.txt",
      "log_raw": true,
      "log_products": true,
      "log_path": "data"
    }


WET Labs ACS
""""""""""""
Example of configuration for a WET Labs ACS.

.. code-block:: json

    {
      "manufacturer": "WetLabs",
      "model": "ACS",
      "serial_number": "301",
      "module": "acs",
      "device_file": "cfg/acs301_20180129.dev",
      "log_raw": true,
      "log_products": true,
      "log_path": "data"
    }

