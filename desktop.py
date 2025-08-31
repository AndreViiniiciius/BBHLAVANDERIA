# desktop.py - Wrapper para abrir o app Flask em janela nativa (sem navegador)
import threading
import socket
import os
import sys
import time

# Importa o app Flask do projeto
import app as webapp

# Ajuste opcional do caminho do banco quando empacotado
# Em modo "onedir", __file__ já aponta para a pasta do app dentro de dist.
# Se quiser forçar a persistência ao lado do executável, descomente abaixo:
# if getattr(sys, "frozen", False):
#     base_dir = os.path.dirname(sys.executable)
#     webapp.BASE_DIR = base_dir
#     webapp.DB_PATH = os.path.join(base_dir, "lavanderia.db")

# Escolhe uma porta livre
def get_free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

PORT = get_free_port()

# Sobe o servidor Flask em uma thread
def run_server():
    # Se preferir, instale waitress e use:
    #   from waitress import serve
    #   serve(webapp.app, host="127.0.0.1", port=PORT, threads=4)
    webapp.app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False, threaded=True)

server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# Aguarda o servidor ficar de pé
for _ in range(60):
    try:
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=0.5)
        conn.request("GET", "/login")
        r = conn.getresponse()
        if r.status in (200, 302, 301, 401):
            break
    except Exception:
        time.sleep(0.2)
else:
    print("Falha ao iniciar o servidor Flask.")
    sys.exit(1)

# Abre janela nativa com o app
import webview
title = getattr(webapp, "APP_TITLE", "BBH — Sistema")
window = webview.create_window(title, f"http://127.0.0.1:{PORT}/login", width=1200, height=800, confirm_close=True)
webview.start()

# Encerra o processo todo ao fechar a janela
os._exit(0)
