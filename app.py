from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("LOBSTER_DB_PATH", "/mnt/workspace/lobster_quant.db")
os.environ.setdefault("LOBSTER_CACHE_DIR", "/mnt/workspace/cache")
os.environ.setdefault("LOBSTER_FRONTEND_DIST", str(ROOT / "front" / "dist"))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, proxy_headers=True)
