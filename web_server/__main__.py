import logging

logger = logging.getLogger(__name__)
import uvicorn

from web_server.app import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
