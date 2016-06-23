TODO
====

Bugs:
  + Warning: no data on start refreshing figure too early
  + Update buffer only if new data in instruments otherwise skip update
  + OSX write bin does not save in case of unexpected closure of the computer
  + in WETLabs:Connect: handle this exception (when try multiple acces to port)
      File "/Users/nils/anaconda/envs/Inlinino/lib/python3.4/site-packages/pyserial-3.1.1-py3.4.egg/serial/serialposix.py", line 475, in read
serial.serialutil.SerialException: read failed: device reports readiness to read but returned no data (device disconnected or multiple access on port?)

Improvements:
  + update README.md
  + write INSTALL.md
  + choose license, need to be compatible with QT4  + check that log_data write every minute or so
  + rewrite Arduino's class
  + GUI:Figure:
      + add Y grid, add time stamp on x axis
      + enable under sample (to handle big buffer)
      + add checkbox freeze to free the figure
  + add a Process method in instrument to process data in real-time
      + do it in a low priority thread
  + add class status/event to display error|warning|info
  +
Major update:
  + Web User Interface with Flask
  + Easy installation with pyInstaller
  + GitHub Wiki or ReadTheDoc

Tests:
  + write testing code
