@echo off
rem Isolated test engine: serves frontend\dist-test on port 8002 (production keeps frontend\dist on 8000).
set RACEHYPE_DIST=C:\f1hud_app\frontend\dist-test
cd /d C:\f1hud_app
C:\f1hud_app\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8002
