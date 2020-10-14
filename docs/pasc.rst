.. _pasc:

====
PASC
====

The precision analog to serial converter (PASC) is an optional data acquisition (DAQ) device. PASC is only required to log data from instruments communicating through analog channels. PASC can be built with an Arduino Uno type microcontroller and a precision analog to digital converter such as the Texas Instrument ADS1015 or ADS1115 `developpement boards <https://www.adafruit.com/product/1083>`__. The wiring instructions to build your own are available at `Adafruit website <https://learn.adafruit.com/adafruit-4-channel-adc-breakouts/assembly-and-wiring>`__.

We uploaded the firmware to the microcontroller following these instructions.

    1. Load mcu_firmwares/PASC.cpp in the `Arduino IDE <https://www.arduino.cc/en/main/software>`__:

        1. In ~/Documents/Arduino create a folder PASC/
        2. Copy and rename mcu_firmware/PASC.cpp to ~/Documents/Arduino/PASC/PASC.ino
        3. Load PASC.ino from Arduino Software (File > Open...)

    2. Comment/uncomment appropriate lines in PASC.ino following instructions in comments of the file.
    3. Compile and upload PASC to the microcontroller (button on the top left of Arduino IDE).

PASC Precision and Accuracy Validation
--------------------------------------

The precision and accuracy of the PASC serial number 001 and 002 were assessed with a Fluke 85 III Voltmeter. We found no significant bias and a reasonable root mean square error of (5.3 mV), the data is presented in the Figure below.

    .. figure:: figures/pasc_validation.png
      :scale: 50 %
      :align: center


Configuration in previous versions of Inlinino
----------------------------------------------
The parameters required to setup the PASC with the previous version of Inlinino are:

  + module
  + name
  + frequency
  + gain (for ADS1X15 only)
  + variables

    + pin
    + units

``frequency: < int >``
  Frequency (in Hertz) at which the Arduino will be reading and reporting voltage.

  .. note::
    Theoretical maximum sampling frequency are:

    =======  ========  ========
      Uno    ADS-1015  ADS-1115
    =======  ========  ========
     9600     3300      860
    =======  ========  ========

    Maximum frequency taking into account conversion delay:

    =======  =======  =======  =======  =======  =======
    Number     Uno        ADS-1015           ADS-1115
    -------  -------  ----------------  ----------------
    of PIN     SE_      SE_      DIF_     SE_      DIF_
    =======  =======  =======  =======  =======  =======
       1       50      1000      500      125      62
       2       25       500      250      62       31
       3       16       333       -       41        -
       4       12       250       -       31        -
       5       10        -        -        -        -
    =======  =======  =======  =======  =======  =======

    .. [#SE] SE: Single ended connection
    .. [#DIF] DIF: Differential connection

``gain: < int >``
  *Available only for the ADS1X15 interface.*

  Set gain of ADS-1x15.

  The ADC input range (or gain) can be changed via this parameter.

  Available options are:

  =======  =======  =========  =========  =========
   Gain      VDD       Resolution (1 bit = x mV)
  -------  -------  -------------------------------
     x     (+/- V)     Uno     ADS-1015   ADS-1115
  =======  =======  =========  =========  =========
    2/3     6.144       -         3        0.1875
     -      5.0        4.88       -          -
     1      4.096       -         2        0.125
     2      2.048       -         1        0.0625
     4      1.024       -        0.5      0.03125
     8      0.512       -       0.25      0.015625
    16      0.256       -       0.125     0.0078125
  =======  =======  =========  =========  =========

  .. note::
    A gain of two third is set with ``"gain":23``.

  .. warning::
    Never exceed the VDD +0.3V ! Exceeding the upper or lower limits may damage a channel of your ADC or destroy it !
    Be carefull with this setting, be conservative and start with a gain of 2/3 (``"gain":23``) for an input of +/- 6.144 V

  .. note::
    Gain is displayed on the digital display on the top left of the GUI. Gain setting is recorded in the output log file with the units.

``variables: {}``
  Each pin connected to the board need to be declared in this section.
  Each variable has a name, a pin name and units.

  ``pin: "< string >"``
    Set which pin to read measurments from.

    pin single ended options are:

      + SIN_A0
      + SIN_A1
      + SIN_A2
      + SIN_A3
      + SIN_A4
      + SIN_A5 (available only on Arduino Uno)

    pin differential connections options are (available only on ADS-1X15):

      + DIF_A01
      + DIF_A23

    .. important:
      The code uploaded on the Microcontroller should match the option sent here.

    .. note:
      if an ADS-1X15 is plugged to the Microcontroller, Analog ports 4 and 5 of the Microcontroller cannot be use for analog readings.

Example of configuration for logging data of an analog fluorometer, the WET Labs WSCD. The instrument output is 12 bit 0-5 Volts, as we are taking measurements in very clear water, signal should never go above 3 Volts. In order to match the resolution of the instrument, an ADS-1015 is used with a gain setting of 1x and a frequency of 1 Hz (as the instrument operates at 1 Hz). The <user_cfg.json> file look like: ::

  "instruments":{
    "WSCD_859":{
      "module":"Arduino",
      "name":"ADS1015",
      "frequency":1,
      "gain":1,
      "variables":{
        "fdom":{
          "pin":"SIN_A0",
          "units":"counts"
        }
      }
    }
  }

