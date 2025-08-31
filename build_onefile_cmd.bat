@echo off
REM === BBH Lavanderia - Build ONEFILE (exe unico) =======================
REM Atenção: em ONEFILE o banco pode nao persistir sem ajuste de caminho.
REM Veja README_PACKAGE.txt (Opcao A) para forcar o DB ao lado do .exe.

py -m pip install pywebview waitress
del *.spec 2>nul

py -m PyInstaller --onefile --noconsole --name "BBH-Lavanderia" --icon app.ico ^
  --add-data "static;static" --add-data "templates;templates" desktop.py

echo.
echo === PRONTO (ONEFILE) ===
echo Arquivo: dist\BBH-Lavanderia.exe
pause
