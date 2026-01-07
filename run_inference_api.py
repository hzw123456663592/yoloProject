# run_inference_api.py
from common.settings import load_settings
from inference.api import app
import uvicorn


if __name__ == "__main__":
    s = load_settings()
    # 这里端口你可以在 config.yaml 用其它字段单独配，
    # 先写死 9100 也可以
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9100,
        reload=False,
    )
