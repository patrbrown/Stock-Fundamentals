@echo off
REM Starts the app and opens it in your browser. Close this window to stop it.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo First-time setup hasn't been run yet. Running setup.bat...
    call setup.bat
)
REM Install any libraries added by an update (fast no-op when everything is present)
".venv\Scripts\python.exe" -c "import sqlalchemy, yfinance, plotly" 2>nul || ".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" -m streamlit run app.py
