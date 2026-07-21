@echo off
if "%~1"=="" (
  set /p NEWPW="New password: "
) else (
  set NEWPW=%~1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0apps\api\reset_password.py" "%NEWPW%"
pause
