import os
import uvicorn
from Backend.config import Telegram
from Backend.fastapi.main import app


Port = Telegram.PORT
config = uvicorn.Config(
    app=app,
    host="0.0.0.0",
    port=Port,
    loop="uvloop",
    http="httptools",
    timeout_keep_alive=30,
    timeout_graceful_shutdown=5,
    # Keep container logs readable. Set UVICORN_ACCESS_LOG=true only when
    # request-by-request diagnostics are needed.
    access_log=os.getenv("UVICORN_ACCESS_LOG", "false").strip().lower() in {"1", "true", "yes", "on"},
)
server = uvicorn.Server(config)
