=============
Configuration
=============

All Inlinino's configuration is located in two json files:
  + inlinino/src/cfg/default_cfg.json
  + inlinino/src/cfg/<user_cfg>.json (user specific)

default_cfg.json should not be edited and is loaded at the start of Inlinino before everything.

The configurations files contains 3 sections:
  - Application_
  - Log_
  - Instruments_

The two first are generally setup in default_cfg.json and are less susceptible to be ajusted. The instruments_ section is often the only section in <user_cfg.json>, in case any parameter from default_cfg.json needs to be modified in <user_cfg.json>, the entire section need to copied otherwise parameters will be missing and error will showup when starting Inlinino.

The path to the user specific configuration file should be specified as an argument when starting the application or it can be edited line 16 of inlinino/src/__main__.py

Application
===========
Documentation coming soon !

Log
===
Documentation coming soon !

Instruments
===========
Documentation coming soon !
