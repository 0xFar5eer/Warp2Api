@echo off
setlocal enabledelayedexpansion

echo =========================================
echo      Warp2Api Docker Startup Script
echo =========================================

REM Function to check if a command exists
echo.
echo Checking prerequisites...

set MISSING_DEPS=false

REM Check Docker
where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo [X] Docker is not installed
    set MISSING_DEPS=true
    goto :show_docker_install
) else (
    echo [OK] Docker is installed
)
:after_docker_check

REM Check Docker Compose
where docker-compose >nul 2>nul
if %errorlevel% neq 0 (
    echo [X] Docker Compose is not installed
    set MISSING_DEPS=true
    goto :show_docker_compose_install
) else (
    echo [OK] Docker Compose is installed
)
:after_docker_compose_check

REM Check curl
where curl >nul 2>nul
if %errorlevel% neq 0 (
    echo [X] curl is not installed
    set MISSING_DEPS=true
    goto :show_curl_install
) else (
    echo [OK] curl is installed
)
:after_curl_check

if "%MISSING_DEPS%"=="true" (
    echo.
    echo Please install missing dependencies and run this script again.
    pause
    exit /b 1
)

goto :main

:show_docker_install
echo.
echo Docker/Docker Compose is missing. Please install:
echo   - Download Docker Desktop from: https://www.docker.com/products/docker-desktop
echo   - Docker Desktop includes both Docker and Docker Compose
echo   - Or install via Chocolatey: choco install docker-desktop
echo   - Or install via Scoop: scoop install docker
goto :after_docker_check

:show_docker_compose_install
echo.
echo Docker Compose is missing. Please install:
echo   - If you have Docker Desktop, Docker Compose should be included
echo   - Or install standalone: https://docs.docker.com/compose/install/
goto :after_docker_compose_check

:show_curl_install
echo.
echo curl is missing. Please install:
echo   - Windows 10/11 usually includes curl by default
echo   - Or install via Chocolatey: choco install curl
echo   - Or install via Scoop: scoop install curl
echo   - Or download from: https://curl.se/windows/
goto :after_curl_check

:main
REM Check if .env file exists
if not exist .env (
    echo.
    echo Creating .env file from .env.example...
    if exist .env.example (
        copy .env.example .env >nul
        echo [OK] Created .env file
        echo Please edit .env file to configure your settings
    ) else (
        echo [X] .env.example not found. Please create .env file manually
        pause
        exit /b 1
    )
)

REM Stop all running containers
echo.
echo Stopping Docker Compose services...
docker-compose down

REM Force rebuild without cache
echo.
echo Force rebuilding Docker image (no cache)...
docker-compose build --no-cache

REM Check if build was successful
if %errorlevel% neq 0 (
    echo [X] Docker build failed. Please check the errors above.
    pause
    exit /b 1
) else (
    echo [OK] Docker image rebuilt successfully
)

REM Start services
echo.
echo Starting Docker Compose services...
docker-compose up -d

REM Check if services started
if %errorlevel% neq 0 (
    echo [X] Failed to start Docker services
    pause
    exit /b 1
) else (
    echo [OK] Docker services started successfully
)

REM Wait for health checks
echo.
echo Waiting for services to be healthy...
set max_attempts=60
set attempt=0

:health_check_loop
if %attempt% geq %max_attempts% goto :health_check_timeout

REM Check health on both ports
for /f %%i in ('curl -s -o nul -w "%%{http_code}" "http://localhost:4009/healthz" 2^>nul') do set health_4009=%%i
for /f %%i in ('curl -s -o nul -w "%%{http_code}" "http://localhost:4010/healthz" 2^>nul') do set health_4010=%%i

if "%health_4009%"=="200" if "%health_4010%"=="200" (
    echo [OK] All services are healthy and ready!
    goto :health_check_done
)

set /a attempt+=1
echo Waiting for services... (%attempt%/%max_attempts% seconds^)
timeout /t 1 /nobreak >nul
goto :health_check_loop

:health_check_timeout
echo [X] Services failed to become healthy after %max_attempts% seconds
echo Port 4009 status: %health_4009%
echo Port 4010 status: %health_4010%
echo You can check logs with: docker-compose logs
pause
exit /b 1

:health_check_done

REM Display service information
echo.
echo =========================================
echo        Services are running!
echo =========================================
echo - Protobuf API: http://localhost:4009
echo - OpenAI API:   http://localhost:4010
echo.
echo Useful commands:
echo - View logs:     docker-compose logs -f
echo - Stop services: docker-compose down
echo - Restart:       docker-compose restart
echo.

REM Check API_KEY configuration
for /f "tokens=2 delims==" %%a in ('findstr /b "API_KEY=" .env') do set API_KEY=%%a

if "%API_KEY%"=="" (
    echo Note: API_KEY is empty - no authentication required
) else (
    echo Note: API_KEY is set - authentication required
    echo       Use header: X-API-Key: %API_KEY%
)

echo =========================================
echo.
pause