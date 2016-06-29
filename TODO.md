TODO
====

Bugs:
  + Warning: no data on start refreshing figure too early
  + OSX write bin does not save in case of unexpected closure of the computer
  + in WETLabs:Connect: handle this exception (when try multiple acces to port)
      File "/Users/nils/anaconda/envs/Inlinino/lib/python3.4/site-packages/pyserial-3.1.1-py3.4.egg/serial/serialposix.py", line 475, in read
serial.serialutil.SerialException: read failed: device reports readiness to read but returned no data (device disconnected or multiple access on port?)

Improvements:
  + GUI:Figure:
      + enable under sample (to handle big buffer)
  + add a Process method in instrument to process data in real-time
      + do it in a low priority thread
  + add class status/event to display error|warning|info
Major update:
  + Web User Interface with Flask
  + Easy installation with pyInstaller
  + GitHub Wiki or ReadTheDoc

Tests:
  + write testing code
