@echo off
setlocal
pip install -U pyinstaller pyinstaller-hooks-contrib
pyinstaller --clean --noconfirm --onefile --name BBH-Lavanderia ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --collect-all reportlab ^
  server_launcher.py
echo.
echo Build concluido. EXE em dist\BBH-Lavanderia.exe
pause
