@echo off
rem FoundationUSBCreator.cmd - double-click me to make a Foundation TerminalOS
rem install USB. This just launches Create-FoundationUSB.ps1 (which must sit in
rem the same folder) with administrator rights; all the real logic - and all
rem the safety gates - live in that script.
set "FOUNDATION_USB_SCRIPT=%~dp0Create-FoundationUSB.ps1"
if not exist "%FOUNDATION_USB_SCRIPT%" (
  echo [!] Create-FoundationUSB.ps1 was not found next to this launcher.
  echo     Download both files into the same folder and try again.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList ('-NoProfile','-ExecutionPolicy','Bypass','-NoExit','-File',('\"' + $env:FOUNDATION_USB_SCRIPT + '\"'))"
