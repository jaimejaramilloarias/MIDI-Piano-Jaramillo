@echo off
setlocal enabledelayedexpansion

set APP_NAME=MIDI Piano Jaramillo
set ICON_FILE=G7alt.ico
set MAIN_FILE=main.py
set VENV_DIR=venv

REM Ir a la carpeta donde está este .bat
cd /d %~dp0

echo ==^> Carpeta actual: %CD%

REM Crear venv si no existe
if not exist "%VENV_DIR%" (
    echo ==^> Creando entorno virtual...
    python -m venv "%VENV_DIR%"
)

REM Activar venv
call "%VENV_DIR%\Scripts\activate.bat"

echo ==^> Actualizando pip...
python -m pip install --upgrade pip

echo ==^> Instalando dependencias...
pip install -r requirements.txt
pip install pyinstaller

echo ==^> Construyendo app Windows...
pyinstaller ^
  --clean ^
  --noconfirm ^
  --name "%APP_NAME%" ^
  --windowed ^
  --icon="%ICON_FILE%" ^
  "%MAIN_FILE%"

echo.
echo Listo. EXE creado en: dist\%APP_NAME%\%APP_NAME%.exe

endlocal
pause
