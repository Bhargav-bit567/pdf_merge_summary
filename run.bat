@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv || goto :error
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
)

echo.
echo Make sure Ollama is running and the model is pulled:
echo     ollama pull llama3.2
echo.
echo Open on this PC:   http://localhost:8000
echo Open on your phone (same Wi-Fi): http://YOUR-PC-IP:8000   (find it with: ipconfig)
echo.

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
goto :eof

:error
echo Setup failed. Make sure Python 3.10+ is installed and on your PATH.
pause
exit /b 1
