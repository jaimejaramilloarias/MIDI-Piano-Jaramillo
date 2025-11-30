#!/usr/bin/env bash
set -e

APP_NAME="MIDI Piano Jaramillo"
ICON_FILE="G7alt.icns"
MAIN_FILE="main.py"
VENV_DIR="venv"

# Ir a la carpeta donde está este script
cd "$(dirname "$0")"

echo "==> Usando carpeta: $(pwd)"

# Crear venv si no existe
if [ ! -d "$VENV_DIR" ]; then
  echo "==> Creando entorno virtual..."
  python3 -m venv "$VENV_DIR"
fi

# Activar venv
source "$VENV_DIR/bin/activate"

echo "==> Actualizando pip..."
pip install --upgrade pip

echo "==> Instalando dependencias..."
pip install -r requirements.txt
pip install pyinstaller

echo "==> Construyendo app macOS..."
pyinstaller \
  --clean \
  --noconfirm \
  --name "$APP_NAME" \
  --windowed \
  --icon="$ICON_FILE" \
  "$MAIN_FILE"

echo
echo "Listo. App creada en: dist/$APP_NAME.app"
