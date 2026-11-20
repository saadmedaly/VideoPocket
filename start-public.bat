@echo off
setlocal enabledelayedexpansion

set ROOT=%~dp0
set BACKEND_DIR=%ROOT%backend
set PROXY_DIR=%ROOT%proxy
set LOG_DIR=%ROOT%logs

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ============================================
echo   VideoPocket - Public Launcher
echo ============================================
echo.

rem ---------------------------------------------------------------
rem Locate cloudflared.exe (winget install, common paths, or PATH)
rem ---------------------------------------------------------------
set CLOUDFLARED=
where cloudflared.exe >nul 2>nul
if %ERRORLEVEL%==0 (
    set CLOUDFLARED=cloudflared.exe
) else if exist "C:\Program Files (x86)\cloudflared\cloudflared.exe" (
    set "CLOUDFLARED=C:\Program Files (x86)\cloudflared\cloudflared.exe"
) else if exist "C:\Program Files\cloudflared\cloudflared.exe" (
    set "CLOUDFLARED=C:\Program Files\cloudflared\cloudflared.exe"
)

if "%CLOUDFLARED%"=="" (
    echo [ERROR] cloudflared.exe not found. Install it with:
    echo     winget install --id Cloudflare.cloudflared -e
    exit /b 1
)

echo [1/4] Starting backend on port 8200...
start "VideoPocket Backend" /min cmd /c ""%BACKEND_DIR%\.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8200 --app-dir "%BACKEND_DIR%" > "%LOG_DIR%\backend.log" 2>&1"

echo [2/4] Starting reverse proxy on port 8090...
set BACKEND_BASE_URL=http://127.0.0.1:8200
start "VideoPocket Proxy" /min cmd /c ""%PROXY_DIR%\.venv\Scripts\python.exe" -m uvicorn proxy:app --host 127.0.0.1 --port 8090 --app-dir "%PROXY_DIR%" > "%LOG_DIR%\proxy.log" 2>&1"

echo [3/4] Waiting for services to become ready...
set READY=0
for /l %%i in (1,1,30) do (
    curl -s -o nul http://127.0.0.1:8090/health
    if !ERRORLEVEL!==0 (
        set READY=1
        goto :ready_done
    )
    timeout /t 1 /nobreak >nul
)
:ready_done

if "!READY!"=="0" (
    echo [ERROR] Services did not become ready in time. Check logs in "%LOG_DIR%".
    exit /b 1
)
echo       Services are up.

echo [4/4] Starting Cloudflare Quick Tunnel...
set TUNNEL_LOG=%LOG_DIR%\cloudflared.log
start "VideoPocket Tunnel" /min cmd /c ""%CLOUDFLARED%" tunnel --url http://127.0.0.1:8090 > "%TUNNEL_LOG%" 2>&1"

echo       Waiting for public URL...
set PUBLIC_URL=
for /l %%i in (1,1,30) do (
    timeout /t 1 /nobreak >nul
    if exist "%TUNNEL_LOG%" (
        for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$m = Select-String -Path '%TUNNEL_LOG%' -Pattern 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' | Select-Object -First 1; if ($m) { $m.Matches[0].Value }"`) do (
            set "PUBLIC_URL=%%A"
        )
    )
    if defined PUBLIC_URL goto :url_done
)
:url_done

echo.
if defined PUBLIC_URL (
    echo ============================================
    echo   VideoPocket is LIVE:
    echo   !PUBLIC_URL!
    echo ============================================
) else (
    echo [WARNING] Could not auto-extract the public URL.
    echo Check "%TUNNEL_LOG%" manually for the trycloudflare.com link.
)

echo.
echo Logs: "%LOG_DIR%"
echo Press any key in this window to stop VideoPocket (backend, proxy, tunnel)...
pause >nul

echo.
echo Stopping VideoPocket services...
taskkill /FI "WINDOWTITLE eq VideoPocket Backend*" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq VideoPocket Proxy*" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq VideoPocket Tunnel*" /T /F >nul 2>nul
echo Done.

endlocal
