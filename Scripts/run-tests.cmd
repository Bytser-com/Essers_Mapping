@echo off
python "%~dp0run-tests.py" %*
exit /b %ERRORLEVEL%