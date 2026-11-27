@echo off
chcp 65001 >nul
REM ============================================================
REM Резервное копирование базы pharmacy_warehouse (PostgreSQL)
REM Файл копии: C:\pharmacy_backup\pharmacy_ГГГГ-ММ-ДД_ЧЧ-ММ.backup
REM Если у вас другая версия PostgreSQL - поменяйте 16 в пути PGBIN.
REM ============================================================
set PGBIN=C:\Program Files\PostgreSQL\16\bin
set PGPASSWORD=ВАШ_ПАРОЛЬ_ПОСТГРЕС
set BACKUP_DIR=C:\pharmacy_backup

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm"') do set DT=%%i

"%PGBIN%\pg_dump.exe" -h localhost -p 5432 -U postgres -F c -f "%BACKUP_DIR%\pharmacy_%DT%.backup" pharmacy_warehouse

if %ERRORLEVEL% EQU 0 (
    echo Копия создана: %BACKUP_DIR%\pharmacy_%DT%.backup
) else (
    echo ОШИБКА при создании копии. Проверьте путь PGBIN и пароль.
)

REM Удаляем копии старше 30 дней
forfiles /p "%BACKUP_DIR%" /m *.backup /d -30 /c "cmd /c del @path" 2>nul
pause
