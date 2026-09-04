@echo off
chcp 6501 >nul 2>&1
cd /d "%~dp0"
title PhoneMarket - подключение аккаунта

echo [*] Проверяю зависимости...
pip install -r requirements.txt -q

python add_account.py
pause
