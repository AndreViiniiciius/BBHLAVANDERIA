@echo off
REM === BBH Lavanderia - Build (CMD) =====================================
REM Requer: Python instalado, pip, e dependências do projeto.
REM OBS: Rode este arquivo NA PASTA DO PROJETO (onde estão app.py e desktop.py).

echo Instalando dependencias...
py -m pip install -r requirements.txt
py -m pip install pywebview waitress

echo Limpando SPEC antigo (se existir)...
del *.spec 2>nul

echo Empacotando (ONEDIR - recomendado p/ persistir banco)...
py -m PyInstaller --onedir --noconsole --name "BBH-Lavanderia" --icon app.ico ^
  --add-data "static;static" --add-data "templates;templates" desktop.py

echo.
echo === PRONTO ===
echo Execute: dist\BBH-Lavanderia\BBH-Lavanderia.exe
pause
