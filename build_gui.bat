@echo off
setlocal
pip install -U pyinstaller pyinstaller-hooks-contrib
pyinstaller --clean --noconfirm --onefile --windowed --noupx --name BBH-Lavanderia-GUI ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --collect-all reportlab ^
  --collect-all webview ^
  --icon "static\logo.ico" ^
  launcher.py
echo.
echo Build concluido. EXE em dist\BBH-Lavanderia-GUI.exe
pause
