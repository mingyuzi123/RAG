@echo off
setlocal
pushd "%~dp0" || exit /b 1
set "PYTHONUTF8=1"
set "RAG_PYTHON=.venv\Scripts\python.exe"
set "RAG_LAB_PORT=8765"
if not "%~2"=="" set "RAG_LAB_PORT=%~2"

if /i "%~1"=="/?" goto help
if /i "%~1"=="--help" goto help
if exist "%RAG_PYTHON%" goto check_python

echo Creating the project virtual environment...
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 goto use_python
py -3 -m venv .venv
if errorlevel 1 goto failed
goto check_python

:use_python
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 goto missing_python
python -m venv .venv
if errorlevel 1 goto failed

:check_python
"%RAG_PYTHON%" -c "import sys; sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 goto missing_python
"%RAG_PYTHON%" -c "import pypdf, pdfplumber" >nul 2>&1
if not errorlevel 1 goto launch
echo Installing PDF dependencies...
"%RAG_PYTHON%" -m pip install -r requirements-pdf-layout.txt
if errorlevel 1 goto failed

:launch
if /i "%~1"=="lab" goto lab
if /i "%~1"=="lab-live" goto lab_live
echo Open the URL printed below. Keep this window open while using RAG Lab.
"%RAG_PYTHON%" scripts\run_demo.py %*
if errorlevel 1 goto failed
goto done

:lab
set "DEEPSEEK_API_KEY="
if exist ".venv\hf\hub\" if not defined HF_HOME (
    set "HF_HOME=%CD%\.venv\hf"
    if not defined HF_HUB_OFFLINE set "HF_HUB_OFFLINE=1"
)
"%RAG_PYTHON%" -m raglab.web --port "%RAG_LAB_PORT%"
if errorlevel 1 goto failed
goto done

:lab_live
"%RAG_PYTHON%" scripts\run_with_deepseek.py --port "%RAG_LAB_PORT%"
if errorlevel 1 goto failed
goto done

:help
echo start.cmd                       Free PDF demo on port 8789
echo start.cmd --live                PDF demo with DeepSeek
echo start.cmd --check               Free demo HTTP self-check, then exit
echo start.cmd --port 8790           PDF demo on a different port
echo start.cmd lab [port]            Full project without an API key ^(default port 8765^)
echo start.cmd lab-live [port]       Full project with DeepSeek ^(default port 8765^)
goto done

:missing_python
echo Python 3.11 or later is required. Install it or recreate this project's .venv.

:failed
echo Startup failed. See the message above.
pause
popd
exit /b 1

:done
popd
exit /b 0
