 import sys, os, threading, webbrowser, time

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

def open_browser():
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:5000")

threading.Thread(target=open_browser, daemon=True).start()

from app import app
if __name__ == "__main__":
    app.run(port=5000, debug=False, use_reloader=False, threaded=True)
