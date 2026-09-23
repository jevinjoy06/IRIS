import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import uvicorn

host = os.environ.get("HUB_HOST", "0.0.0.0")
port = int(os.environ.get("HUB_PORT", "7865"))

uvicorn.run("hub.server:app", host=host, port=port, reload=True)
