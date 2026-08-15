@echo off
setlocal
set "PROJECT_ROOT=%~dp0.."
set "JAVA_HOME=%PROJECT_ROOT%\.tooling\jdk-21"
set "PATH=%JAVA_HOME%\bin;%PATH%"
call "%PROJECT_ROOT%\.tooling\apache-maven\bin\mvn.cmd" %*
exit /b %ERRORLEVEL%
