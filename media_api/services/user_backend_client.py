# media_api/services/user_backend_client.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import base64
import os
from datetime import datetime

import requests


@dataclass
class UserBackendClient:
    base_url: str
    warning_path: str = "/addVideo/warning"
    timeout: int = 10

    @property
    def url(self) -> str:
        return self.base_url.rstrip("/") + self.warning_path

        # ★★★ 新增：简单写日志到文件的工具方法 ★★★

    def _log(self, text: str) -> None:
        """
        把调用信息写到日志文件：
        logs/user_backend.log
        """
        # 日志文件路径（项目根目录下的 logs/user_backend.log）
        log_path = Path("logs") / "user_backend.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {text}\n")

    def send_alarm(
        self,
        *,
        image_path: Path,
        video_path: Path,
        sensor_id: str,
        msg: str,
        ts: int,
    ) -> Optional[dict]:
        """
        image 作为 base64 字符串发送;
        video 作为 multipart/form-data 的文件流发送。
        表单字段约定：
          - image: base64 字符串
          - video: 文件（mp4）
          - id:    传感器 / 摄像头 id
          - msg:   告警行为
          - time:  告警时间（字符串）
        """
        # 1) 读取图片并转 base64
        with image_path.open("rb") as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode("ascii")

        # 2) 组装 form-data 里的普通字段
        time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        data = {
            "image": img_b64,
            "id": sensor_id,
            "msg": msg,
            "time": time_str,
        }

        # 3) 组装文件字段（video = mp4 文件流）
        filename = os.path.basename(str(video_path))
        video_size = video_path.stat().st_size  # 字节数

        # ★★★ 把即将发送的内容写到日志文件 ★★★
        preview = img_b64[:100]  # 只截取前 100 个字符，避免日志太大
        log_text = (
            f"POST {self.url}\n"
            f"  id   = {sensor_id}\n"
            f"  msg  = {msg}\n"
            f"  time = {time_str}\n"
            f"  image_base64_length = {len(img_b64)}\n"
            f"  image_base64_preview = {preview}...\n"
            f"  video.filename = {filename}\n"
            f"  video.size     = {video_size} bytes"
        )
        self._log(log_text)


        with video_path.open("rb") as vf:
            files = {
                "video": (filename, vf, "video/mp4")
            }
            resp = requests.post(self.url, data=data, files=files, timeout=self.timeout)

        try:
            resp.raise_for_status()
        except Exception as e:
            print("[UserBackendClient] send_alarm failed:", e, "status:", resp.status_code, "text:", resp.text)
            return None

        try:
            return resp.json()
        except Exception:
            return None

        # ★ 成功结果也可以简单记一下
        self._log(f"send_alarm success, response={result}")
        return result



# media_api/services/user_backend_client.py
# from __future__ import annotations
# from dataclasses import dataclass
# from pathlib import Path
# from typing import Optional
# import base64
# import os
# from datetime import datetime
# import io
#
# import requests
#
#
# @dataclass
# class UserBackendClient:
#     base_url: str
#     warning_path: str = "/addVideo/warning"
#     timeout: int = 10
#
#     @property
#     def url(self) -> str:
#         return self.base_url.rstrip("/") + self.warning_path
#
#     # ★★★ 写日志到文件的工具方法：logs/user_backend.log ★★★
#     def _log(self, text: str) -> None:
#         """
#         把调用信息写到日志文件：
#         logs/user_backend.log
#         """
#         log_path = Path("logs") / "user_backend.log"
#         log_path.parent.mkdir(parents=True, exist_ok=True)
#
#         ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         with log_path.open("a", encoding="utf-8") as f:
#             f.write(f"[{ts}] {text}\n")
#
#     def send_alarm(
#         self,
#         *,
#         image_path: Path,
#         video_path: Path,
#         sensor_id: str,
#         msg: str,
#         ts: int,
#     ) -> Optional[dict]:
#         """
#         image 作为 base64 字符串发送;
#         video 作为 multipart/form-data 的文件流发送。
#         表单字段约定：
#           - image: base64 字符串
#           - video: 文件（mp4）
#           - id:    传感器 / 摄像头 id
#           - msg:   告警行为
#           - time:  告警时间（字符串）
#         并且：把完整的 image base64 和完整的 video（转成 base64）都记录到日志。
#         """
#         # 1) 读取图片并转 base64（完整保存）
#         with image_path.open("rb") as f:
#             img_bytes = f.read()
#         img_b64 = base64.b64encode(img_bytes).decode("ascii")
#
#         # 2) 读取视频文件（完整读取），用于：
#         #    - 发送（作为文件流）
#         #    - 日志（转成 base64 文本写入）
#         with video_path.open("rb") as vf:
#             video_bytes = vf.read()
#         video_b64 = base64.b64encode(video_bytes).decode("ascii")
#
#         # 3) 组装 form-data 里的普通字段
#         time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
#         data = {
#             "image": img_b64,
#             "id": sensor_id,
#             "msg": msg,
#             "time": time_str,
#         }
#
#         filename = os.path.basename(str(video_path))
#         video_size = len(video_bytes)
#
#         # ★★★ 把“将要发送的全部内容”写到日志文件 ★★★
#         log_text = (
#             f"POST {self.url}\n"
#             f"  id   = {sensor_id}\n"
#             f"  msg  = {msg}\n"
#             f"  time = {time_str}\n"
#             f"  image_base64_length = {len(img_b64)}\n"
#             f"  image_base64 = {img_b64}\n"
#             f"  video.filename = {filename}\n"
#             f"  video.size     = {video_size} bytes\n"
#             f"  video_base64_length = {len(video_b64)}\n"
#             f"  video_base64 = {video_b64}"
#         )
#         self._log(log_text)
#
#         # 4) 真正发送请求
#         #    因为前面已经把 video_bytes 读出来了，这里用 BytesIO 包一下当文件流
#         files = {
#             "video": (filename, io.BytesIO(video_bytes), "video/mp4")
#         }
#         try:
#             resp = requests.post(self.url, data=data, files=files, timeout=self.timeout)
#         except Exception as e:
#             # 网络级错误（连不上/超时）
#             self._log(f"send_alarm request exception: {e!r}")
#             return None
#
#         # 5) 处理 HTTP 状态码
#         if not resp.ok:
#             self._log(
#                 f"send_alarm failed: status={resp.status_code}, "
#                 f"text={resp.text[:500]}..."  # 这里只是响应体截断一下，避免太长
#             )
#             return None
#
#         # 6) 尝试解析 JSON，并写成功日志
#         try:
#             result = resp.json()
#         except Exception:
#             result = None
#
#         self._log(f"send_alarm success, response={result}")
#         return result

