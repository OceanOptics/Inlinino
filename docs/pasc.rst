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

    .. image:: figures/pasc_validation.png