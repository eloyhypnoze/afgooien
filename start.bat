@echo off
cd /d "%~dp0"
where py >NUL 2>NUL
if %errorlevel%==0 (py -3 run.py %*) else (python run.py %*)
pause
