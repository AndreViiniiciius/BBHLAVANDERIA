import time, threading
from waitress import serve
try:
    import webview
except Exception:
    webview = None
from app import app
def run_server():
    serve(app, host="127.0.0.1", port=5000)
if __name__ == "__main__":
    t = threading.Thread(target=run_server, daemon=True); t.start()
    time.sleep(1)
    if webview:
        webview.create_window("BBH — Lavanderia", "http://127.0.0.1:5000", width=1200, height=800)
        webview.start()
    else:
        import webbrowser
        webbrowser.open("http://127.0.0.1:5000"); t.join()
