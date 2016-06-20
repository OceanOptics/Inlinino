TODO
====

Bugs:
  + update README.md
  + write INSTALL.md
  + choose license, need to be compatible with QT4  + check that log_data write every minute or so
  + Bug line log.py:199 index out of range in some cases
  + Warning: no data on start refreshing figure too early
  + pySerial compatibility with python 3.x

Improvements:
  + rewrite Arduino's class
  + Graphical User Interface with QT
      + Clean code
  + add a Process method in instrument to process data in real-time
      + do it in a low priority thread
  + instrument.m_nNonResponse should be reset after every new file (and not otherwise)
  + add class status/event to display error|warning|info
  + add parameter robust for listing com ports

Major update:
  + Web User Interface with Flask
  + Easy installation with pyInstaller
  + GitHub Wiki or ReadTheDoc

Tests:
  + write tests
    + test all lines of code
    + various test
  + test on PC
