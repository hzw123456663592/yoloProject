from common.settings import load_settings
from media_api.main import app
import uvicorn


if __name__ == "__main__":
    s = load_settings()
    uvicorn.run(
        app,
        host=s.server.get("host", "0.0.0.0"),
        port=int(s.server.get("port", 9000)),
        reload=False,
    )
