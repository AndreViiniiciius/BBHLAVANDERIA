# BBH Lavanderia - Empacotamento Windows (sem navegador)

1) Pré-requisitos
- Python 3.10+ instalado
- WebView2 Runtime (Windows). Se a janela nao abrir, instale o runtime da Microsoft.
- Dentro da pasta do projeto, os arquivos: app.py, desktop.py, requirements.txt, templates/, static/

2) Passo a passo rápido (CMD)
- Clique duas vezes em: run_test.cmd  (para testar sem empacotar). Se abriu a janela, ok.
- Depois clique em: build_cmd.bat     (gera dist\BBH-Lavanderia\BBH-Lavanderia.exe)

3) ONEFILE (exe único)
- Use build_onefile_cmd.bat
- Se quiser persistir o banco ao lado do .exe, edite desktop.py e descomente o bloco:
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
        webapp.BASE_DIR = base_dir
        webapp.DB_PATH = os.path.join(base_dir, "lavanderia.db")

4) Problemas comuns
- 'No module named webview' -> pip install pywebview
- Janela nao abre / erro de backend -> instale o WebView2 Runtime (Microsoft)
- 'Script file ... does not exist' -> rode os .bat dentro da pasta do projeto
- PDF/ReportLab: se nao gerar, verifique se reportlab esta instalado (requirements.txt)

5) Onde fica o banco?
- ONEDIR: fica na pasta dist\BBH-Lavanderia (persistente).
- ONEFILE: precisa ajustar DB_PATH (ver item 3).
