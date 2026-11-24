"""Desktop app launcher for the agent controller.

Run from the project root:   python app.py

Starts the existing local controller server on a free port and shows it
in a native window (pywebview) instead of the system browser.
"""

import threading
from http.server import ThreadingHTTPServer

from agent_controller.web_ui import HOST, PROJECT_ROOT, Handler


def main():
    try:
        import webview
    except ImportError:
        raise SystemExit("pywebview is missing. Run: pip install -r requirements.txt")

    # Port 0 = let the OS pick a free port, so the app never clashes with
    # a running web_ui instance.
    server = ThreadingHTTPServer((HOST, 0), Handler)
    url = f"http://{HOST}:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    webview.create_window(
        f"Agent World - {PROJECT_ROOT.name}", url, width=1280, height=820
    )
    try:
        webview.start()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
