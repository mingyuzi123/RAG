@echo off
rem Called from the repository root by the Windows launchers.
set "PYTHONUTF8=1"
set "RAG_PYTHON=.venv\Scripts\python.exe"
if exist "%RAG_PYTHON%" goto check_python

echo Creating the project virtual environment...
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 goto use_python
py -3 -m venv .venv
if errorlevel 1 exit /b 1
goto check_python

:use_python
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 goto missing_python
python -m venv .venv
if errorlevel 1 exit /b 1

:check_python
"%RAG_PYTHON%" -c "import sys; sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 goto missing_python
"%RAG_PYTHON%" -c "import pypdf, pdfplumber" >nul 2>&1
if not errorlevel 1 exit /b 0
echo Installing PDF dependencies...
"%RAG_PYTHON%" -m pip install -r requirements-pdf-layout.txt
exit /b %errorlevel%

:missing_python
echo Python 3.11 or later is required. Install it or recreate this project's .venv.
exit /b 1
