import socket
import sys
from pathlib import Path

import uvicorn

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.main import app


def get_local_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "unknown"


if __name__ == "__main__":
    ip = get_local_ip()
    print("\n  >> History Timeline Project")
    print("  >> Local:    http://localhost:8000")
    print(f"  >> Network:  http://{ip}:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
