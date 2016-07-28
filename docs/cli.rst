.. _cli:

======================
Command Line Interface
======================

The command line interface of Inlinino is can be very handy when logging data on limited resources such as Raspberry Pi or when running on a server.

Once the Inlinino is started with a command ``python -O src`` it will display a header and wait for a command.::

  Inlinino 2.0 alpha (May 16, 2016)
  Type "help", "support", or "credits" for more information.
  >>

.. hint::
  Help can be found at anytime. Typing ``help`` will print a list of the command available. To get help on a specific command write ``help <command>`` replacing <command> with the name of the command you need some explanations.::

    >>help

    List of commands available (type help <topic>):
    ===============================================
    EOF  credits  exit  help  instrument  log  shell  status  support

    >>help log
    log [arg]
      <start> logging data
      <stop> logging data
      <header> change file name header
      <filename> return current filename
    >>

.. tip::
  Autocompletion is enabled for each command pressing [tab] as you would do it on any bash or zsh terminal.
  A history of the command entered is kept in memory, they can be called by using the up arrow on your keyboard as you would do it on any bash or szh terminal.
  It's possible to run any command from bash by starting the command with ``!``. ::

    >>!pwd
    /Users/nils/Documents/UMaine/Lab/Inline/inlinino

    >>

.. contents:: Table of Contents

Instrument
==========
The set of command starting with ``instrument`` allow to connect/disconnect or display information regarding the instruments.

``instrument connect <instrument_name> [<instrument_port>]``
  Connect the instrument named ``<instrument_name>``.
  If the instrument requires a port you should specify it in last argument ``<instrument_port>``. ::

    >>instrument connect SimulinoSin
    >>

``instrument close <instrument_name>``
  Disconnect instruments named ``<instrument_name>``. ::

    >>instrument close SimulinoSin
    >>

``instrument list [ports]``
  List all instruments
  If ``ports`` is specified in the command it will list all ports available on the computer. ::

    >>instrument list
    SimulinoSin
    SimulinoRnd
    >>instrument list ports
    /dev/cu.Bluetooth-Incoming-Port: n/a
    /dev/cu.iPhone-WirelessiAP: n/a
    >>

``instrument read [<instrument_name>]``
  Read data from the instrument matching ``<instrument_name>``.
  If no ``<instrument_name>`` is specified it will read from all instruments. ::

    >>instrument read
    {'sin': 2.212096683334974, 'sin_noise': 0.06595185215313082}
    {'rnd2': 0.6670297159334724, 'rnd1': 1.4078267848958586}
    >>instrument read SimulinoSin
    {'sin': 1.6628582219802706, 'sin_noise': 0.3032862396665401}
    >>

Log
===
The set of command starting with ``log`` allow to save data from instruments.

``log start``
  Start logging data. ::

    >>log start
    Start logging data.
    >>

``log stop``
  Stop logging data. ::

    >>log stop
    Stop logging data.
    >>

.. _cli-header:

``log header <filename_prefix>``
  Change the log files prefix by the one specified in ``<filename_prefix>``. You can check the modification with the command ``log filename``. ::

    >>log header Inlinino
    >>

``log filename``
  Display the path to current logging file. Note that if the path is relative you can get the current directory from which Inlinino is running with ``!pwd`` ::

    >>log filename
    data/Inlinino_yyyymmdd_HHMMSS.csv
    >>


Status
======
``status``
  Display current status of the application, few information regarding the verbosity of the software as well as if the instruments are connected or not are displayed. ::

    >>status
    [Configuration]
      verbosity:2
    [Instruments]
      SimulinoSin[active]
      SimulinoRnd[active]

Exit
====
The application can be closed at anytime. Data is saved before exiting even if the user did not stop logging before exiting.

``exit`` or ``EOF``
  Exit command line interface and quit Inlinino.
  When application is closed properly: ::

    >>EOF
    (Inlinino)

  When application is closed and logging or instruments are still running: ::

    >>exit
    Closing connection with SimulinoRnd
    Stop logging data.
    Stop buffer thread.
    (Inlinino)

``[Ctrl]+[C]``
  Applications will try to exit properly, saving all the data and closing serial connection. ::

    >>^CKeyboard Interrupt received.
    Trying to close connection with instrument(s), to save data and close log file properly.
    Closing connection with SimulinoRnd
    Stop logging data.
    Stop buffer thread.
    (Inlinino)

  If you press several times ``[Ctrl]+[C]`` some python errors will show up and data might be lost.
