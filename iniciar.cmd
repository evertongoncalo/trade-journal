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
netstat -ano | findstr /R /C:":8765 .*LISTENING" >nul
if not errorlevel 1 (
  echo A porta 8765 ja esta em uso, provavelmente por uma execucao anterior do app.
  echo Feche a outra janela ou encerre o processo e tente de novo.
  exit /b 1
)
echo Abra http://127.0.0.1:8765 no navegador. Ctrl+C para encerrar.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
