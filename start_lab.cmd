@echo off
setlocal
pushd "%~dp0" || exit /b 1
if /i "%~1"=="/?" goto help
if /i "%~1"=="--help" goto help

call scripts\prepare_windows.cmd
if errorlevel 1 goto failed
echo Open the URL printed below. Keep this window open while using RAG Lab.
set "RAG_LAB_PORT=8765"
set "RAG_KEY_MODE=--auto-key"
if /i "%~1"=="--live" (
    set "RAG_KEY_MODE="
    shift
) else if /i "%~1"=="--offline" (
    set "RAG_KEY_MODE=--offline"
    shift
)
if not "%~1"=="" set "RAG_LAB_PORT=%~1"
"%RAG_PYTHON%" scripts\run_with_deepseek.py %RAG_KEY_MODE% --port "%RAG_LAB_PORT%"
if errorlevel 1 goto failed
goto done

:help
echo start_lab.cmd [port]             Use DeepSeek when configured ^(default port 8765^)
echo start_lab.cmd --live [port]      Require a DeepSeek key from .env or the environment
echo start_lab.cmd --offline [port]   Free retrieval without DeepSeek
goto done

:failed
echo Startup failed. See the message above.
pause
popd
exit /b 1

:done
popd
exit /b 0
