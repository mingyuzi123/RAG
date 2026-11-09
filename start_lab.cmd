@echo off
setlocal
pushd "%~dp0" || exit /b 1
if /i "%~1"=="/?" goto help
if /i "%~1"=="--help" goto help

call scripts\prepare_windows.cmd
if errorlevel 1 goto failed
echo Open the URL printed below. Keep this window open while using RAG Lab.
set "RAG_LAB_PORT=8765"
if /i "%~1"=="--live" goto live
if not "%~1"=="" set "RAG_LAB_PORT=%~1"
set "DEEPSEEK_API_KEY="
if exist ".venv\hf\hub\" if not defined HF_HOME (
    set "HF_HOME=%CD%\.venv\hf"
    if not defined HF_HUB_OFFLINE set "HF_HUB_OFFLINE=1"
)
"%RAG_PYTHON%" -m raglab.web --port "%RAG_LAB_PORT%"
if errorlevel 1 goto failed
goto done

:live
if not "%~2"=="" set "RAG_LAB_PORT=%~2"
"%RAG_PYTHON%" scripts\run_with_deepseek.py --port "%RAG_LAB_PORT%"
if errorlevel 1 goto failed
goto done

:help
echo start_lab.cmd [port]          Full project without an API key ^(default port 8765^)
echo start_lab.cmd --live [port]   Full project with DeepSeek from .env or the environment
goto done

:failed
echo Startup failed. See the message above.
pause
popd
exit /b 1

:done
popd
exit /b 0
