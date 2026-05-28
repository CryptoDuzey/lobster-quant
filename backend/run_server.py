# coding: utf-8
from __future__ import annotations

import traceback
from pathlib import Path


LOG_FILE = Path(__file__).resolve().with_name("server_startup_error.log")


def main() -> None:
    try:
        try:
            from dotenv import load_dotenv

            load_dotenv(Path(__file__).resolve().with_name(".env"))
        except Exception:
            pass

        import uvicorn

        uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
    except Exception:
        LOG_FILE.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
