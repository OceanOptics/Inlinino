Inlinino
========

Inlinino is a simple data logger. It is design to log data from any WETLabs instruments (BB3 implemented, other will be available soon), read Analog ports from an Arduino (with or without ADC) or any instruments for which a python API is available. It's primarely design to log oceanographic data inline but can be adapted to any application. Data is logged in csv files that can be imported easily in most of the data analysis software (Matlab, R, or Python).

This code was tested during the [NAAMES](http://naames.larc.nasa.gov) cruise runnning 30 days in a row and is currently logging data on the Research Vessel [Tara](http://oceans.taraexpeditions.org/). It's compatible with Windows 7 (probably 8 and 10 but not tested), OSX and should be working on common Linux distribution (not tested).

The application is written in python 3.4, on top of pySerial and numpy. Two user interface are available to date: a graphical user interface (GUI) based on PyQt and a command line interface (CLI). A web interface will be implemented if time allows in order to visiualize data in real-time on ships network.

The application was developped by Nils Haëntjens <nils.haentjens+inlinino@maine.edu>.

This code could be modified to control instruments but similar project already does it very well: Instrumentino.