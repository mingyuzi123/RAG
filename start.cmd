@echo off
setlocal
pushd "%~dp0" || exit /b 1
if /i "%~1"=="/?" goto help
if /i "%~1"=="--help" goto help
if /i "%~1"=="lab" goto lab
if /i "%~1"=="lab-live" goto lab_live

call scripts\prepare_windows.cmd
if errorlevel 1 goto failed
echo Open the URL printed below. Keep this window open while using RAG Lab.
"%RAG_PYTHON%" scripts\run_demo.py %*
if errorlevel 1 goto failed
goto done

:lab
call start_lab.cmd "%~2"
goto return_result

:lab_live
call start_lab.cmd --live "%~2"
goto return_result

:return_result
set "RAG_EXIT_CODE=%errorlevel%"
popd
exit /b %RAG_EXIT_CODE%

:help
echo start.cmd                       Free PDF demo on port 8789
echo start.cmd --live                PDF demo with DeepSeek
echo start.cmd --check               Free demo HTTP self-check, then exit
echo start.cmd --port 8790           PDF demo on a different port
echo start_lab.cmd                   Separate launcher for the full project
goto done

:failed
echo Startup failed. See the message above.
pause
popd
exit /b 1

:done
popd
exit /b 0
