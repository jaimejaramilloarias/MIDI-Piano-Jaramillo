MIDI Piano Jaramillo para Windows
=================================

Contenido
---------
Este paquete es un kit de construccion para Windows. Incluye:
- main.py
- music_theory.py
- requirements.txt
- build_win.bat
- G7alt.ico
- diccionario_acordes.json
- assets/
- tests/

Importante
----------
PyInstaller no puede generar un .exe de Windows desde macOS. El .exe debe construirse en Windows.
Este paquete deja todo listo para generar el ejecutable con doble clic en build_win.bat.

Requisitos en Windows
---------------------
- Windows 10 u 11, 64-bit.
- Python 3.12 o 3.13 recomendado, 64-bit.
- Conexion a internet la primera vez para instalar dependencias.

Construccion del .exe
---------------------
1. Descomprime este ZIP en una carpeta sin caracteres raros.
2. Instala Python para Windows desde https://www.python.org/downloads/windows/
3. Marca "Add python.exe to PATH" durante la instalacion.
4. Haz doble clic en build_win.bat.
5. Al terminar, el ejecutable queda en:
   dist\MIDI Piano Jaramillo\MIDI Piano Jaramillo.exe

Uso
---
Abre MIDI Piano Jaramillo.exe. Para MIDI en vivo, conecta tu teclado antes de abrir la app
o refresca entradas desde el menu MIDI.

Descripcion
-----------
MIDI Piano Jaramillo es una aplicacion de practica y visualizacion armonica para teclado MIDI.
Muestra teclado, cifrado de acordes, partitura, escalas pregrabadas, acordes pregrabados,
etiquetas funcionales de intervalos, alertas de 9m segun contexto armonico y controles de
octavas/registro en una interfaz moderna.

Nota sobre distribucion
-----------------------
El primer .exe generado por PyInstaller puede activar Windows SmartScreen porque no esta firmado
con certificado comercial. Si se va a distribuir publicamente, conviene firmarlo con un certificado
de codigo para Windows.
