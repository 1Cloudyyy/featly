@echo off
REM Featly Engine — Import Task Scheduler task
REM Run this once to set up auto-start

echo Importing Featly Engine task...
schtasks /create /tn "FeatlyEngine" /xml "%~dp0featly-engine-task.xml" /f
echo.
echo Task imported successfully!
echo Engine will start automatically on next login.
echo.
echo To start manually: schtasks /run /tn "FeatlyEngine"
echo To remove: schtasks /delete /tn "FeatlyEngine" /f
pause
