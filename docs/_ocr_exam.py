"""临时 OCR 脚本：用硅基流动 Qwen3-VL-32B-Instruct 转录试卷图片。

仅用于整理示例题库文本，不写入仓库中的密钥，也不提交原始试卷图片。
"""
import base64
import json
import os
import sys
import time

import requests
from dotenv import dotenv_values

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = dotenv_values(os.path.join(ROOT, "backend-example", ".env"))
API_KEY = ENV.get("api_key", "")
BASE_URL = ENV.get("base_url", "https://api.siliconflow.cn/v1").rstrip("/")
MODEL = "Qwen/Qwen3-VL-32B-Instruct"
PROMPT = (
    "请逐字转录这张数学试卷图片中的全部可见文字，保留题号、选项、答案与解析。"
    "只输出转录内容，使用 Markdown 排版，不要总结、不要遗漏题目。"
    "如果图片中有与有理数加减法无关的题，也请保留原题号。"
)


def ocr(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    resp = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=180,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


if __name__ == "__main__":
    targets = sys.argv[1:] or [
        os.path.join(ROOT, "docs", "exam_pages", f"page{i}.png") for i in range(1, 9)
    ]
    out_dir = os.path.join(ROOT, "docs", "exam_pages", "ocr")
    os.makedirs(out_dir, exist_ok=True)
    for path in targets:
        name = os.path.splitext(os.path.basename(path))[0]
        print(f"[OCR] {name} ...", flush=True)
        try:
            text = ocr(path)
        except Exception as exc:
            print(f"[OCR] {name} FAILED: {exc}", flush=True)
            continue
        with open(os.path.join(out_dir, f"{name}.md"), "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[OCR] {name} OK, {len(text)} chars", flush=True)
        time.sleep(1)
