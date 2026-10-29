@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Episode Player

rem Resolve a dragged folder before switching to the project directory.
set "PLAYER_SOURCE="
if not "%~1"=="" set "PLAYER_SOURCE=%~f1"
pushd "%~dp0"
if errorlevel 1 exit /b 1

if not exist ".conda-env" goto missing_env
set "PLAYER_ENV="
set /p "PLAYER_ENV="<".conda-env"
if not defined PLAYER_ENV goto missing_env

set "PLAYER_CONDA=%USERPROFILE%\anaconda3\Scripts\conda.exe"
if exist "%PLAYER_CONDA%" goto launch
if defined CONDA_EXE set "PLAYER_CONDA=%CONDA_EXE%"
if exist "%PLAYER_CONDA%" goto launch
echo Conda was not found. Check your Anaconda installation or CONDA_EXE.
goto failed

:launch
set "PYTHONDONTWRITEBYTECODE=1"
if defined PLAYER_SOURCE goto with_source
if exist "..\..\SwarmData\parallel_batch\v06_pilot30b_seed2026100811\dataset\dataset_manifest.json" set "PLAYER_SOURCE=%CD%\..\..\SwarmData\parallel_batch\v06_pilot30b_seed2026100811"
if defined PLAYER_SOURCE goto with_source
"%PLAYER_CONDA%" run -n "%PLAYER_ENV%" --no-capture-output python -B -m episode_player
goto finished

:with_source
"%PLAYER_CONDA%" run -n "%PLAYER_ENV%" --no-capture-output python -B -m episode_player --source "%PLAYER_SOURCE%"

:finished
if errorlevel 1 goto failed
popd
exit /b 0

:missing_env
echo The project .conda-env file is missing or empty.

:failed
echo.
echo Episode Player could not start. See the error above.
pause
popd
exit /b 1
