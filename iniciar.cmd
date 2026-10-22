@echo off
rem Inicia o Trade Journal (backend + frontend compilado) em http://127.0.0.1:8765
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente Python nao encontrado. Veja o README, secao "Como rodar".
  exit /b 1
)
if not exist "..\frontend\dist\index.html" (
  echo Aviso: frontend nao compilado. Rode "npm install" e "npm run build" na pasta frontend.
)
echo Abra http://127.0.0.1:8765 no navegador. Ctrl+C para encerrar.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
