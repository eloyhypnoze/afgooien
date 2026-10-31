@echo off
rem Afgooien met een klik: server starten en het speelscherm openen in Chrome.
rem Opties kun je erachter zetten, bijv.:  Afgooien.bat --autodarts off   of   --kiosk   of   --browser edge
cd /d "%~dp0"
title Afgooien
where py >NUL 2>NUL
if %errorlevel%==0 (py -3 launcher.py %*) else (python launcher.py %*)
if errorlevel 1 pause
