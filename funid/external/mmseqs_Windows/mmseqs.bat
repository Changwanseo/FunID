@echo off
if not exist "%~dp0\bin\bash" ( goto installBusyBox )
goto binary

:installBusyBox
"%~dp0\bin\busybox.exe" --install -s "%~dp0\bin" > nul 2>&1
if not exist "%~dp0\bin\bash" ( goto installBusyBoxUAC )
goto binary

:installBusyBoxUAC
echo Administrator permissions will now be requested to install helper tools through Busybox.
echo WScript.Sleep 2000 > "%temp%\~ElevateBusyBox.vbs"
echo set UAC = CreateObject^("Shell.Application"^) >> "%temp%\~ElevateBusyBox.vbs"
echo UAC.ShellExecute "%~dp0\bin\busybox.exe", "--install -s ""%~dp0\bin""", , "runas", 0 >> "%temp%\~ElevateBusyBox.vbs"
echo WScript.Sleep 2000 >> "%temp%\~ElevateBusyBox.vbs"
cscript "%temp%\~ElevateBusyBox.vbs" > nul 2>&1
del /Q /F "%temp%\~ElevateBusyBox.vbs"
if not exist "%~dp0\bin\bash" ( goto noBusyBox )
goto binary

:binary
"%~dp0\bin\mmseqs.exe" %*
exit /b 0

:noBusyBox
echo Error: Could not install BusyBox helper tools. Please execute the following command manually: >&2
echo "%~dp0\bin\busybox.exe" --install -s "%~dp0\bin" >&2
exit /b 1
