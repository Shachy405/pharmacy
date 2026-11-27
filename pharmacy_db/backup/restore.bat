@echo off
chcp 65001 >nul
REM ============================================================
REM Восстановление базы из резервной копии.
REM Использование: restore.bat "C:\pharmacy_backup\pharmacy_2026-10-19_18-00.backup"
REM Сначала в pgAdmin создайте ПУСТУЮ базу pharmacy_warehouse_restored.
REM ============================================================
set PGBIN=C:\Program Files\PostgreSQL\16\bin
set PGPASSWORD=ВАШ_ПАРОЛЬ_ПОСТГРЕС

if "%~1"=="" (
    echo Укажите файл копии: restore.bat "путь\к\файлу.backup"
    pause
    exit /b 1
)

"%PGBIN%\pg_restore.exe" -h localhost -p 5432 -U postgres -d pharmacy_warehouse_restored --no-owner "%~1"

if %ERRORLEVEL% EQU 0 (
    echo База восстановлена в pharmacy_warehouse_restored
) else (
    echo ОШИБКА при восстановлении.
)
pause
