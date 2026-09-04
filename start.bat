@echo off
chcp 6501 >nul 2>&1
cd /d "%~dp0"
title PhoneMarket - продажа телефонов

if not exist ".env" (
  echo [*] Создаю .env из .env.example...
  copy ".env.example" ".env" >nul
)

echo [*] Проверяю зависимости...
pip install -r requirements.txt -q

echo [*] Запускаю сервер...
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:5000"

python app.py
pause
