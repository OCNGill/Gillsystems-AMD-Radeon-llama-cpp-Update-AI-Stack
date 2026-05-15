@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: Gillsystems AI Stack Updater - Windows Launcher
:: update-ai-stack.bat
::
:: On every run:
::   - Elevates to Administrator (UAC prompt if not already admin)
::   - Calls bootstrap.ps1 which handles Python find/install,
::     PATH updates, pip, dependencies, and running the agent
::   - Window always stays open so errors can be read/copied
:: ============================================================

cd /d "%~dp0"

:: -- Admin elevation (skipped in --dry-run) --
SET IS_DRYRUN=0
FOR %%A IN (%*) DO IF /I "%%A"=="--dry-run" SET IS_DRYRUN=1

NET SESSION >nul 2>&1
IF !ERRORLEVEL! NEQ 0 (
    IF !IS_DRYRUN! EQU 0 (
        echo  [Gillsystems] Requesting Administrator privileges...
        powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
        exit /b
    )
    echo  [Gillsystems] Dry-run mode - continuing without admin.
    echo.
)

:: -- Run the full bootstrap + agent via PowerShell --
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" %*
SET EXIT_CODE=!ERRORLEVEL!

echo.
IF !EXIT_CODE! NEQ 0 IF !EXIT_CODE! NEQ 130 (
    echo  [Gillsystems] *** ERROR ***  Exit code: !EXIT_CODE!
    echo  Logs check: %~dp0logs\
    echo.
)
pause
exit /b !EXIT_CODE!
