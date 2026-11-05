"""硅基流动模型客户端（LangChain OpenAI 兼容接口）+ 结构化输出修复。"""
from __future__ import annotations

import json
import sys
from typing import Optional, Type

from pydantic import BaseModel, ValidationError

from .config import settings
from .json_utils import extract_json

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
except Exception as exc:  # pragma: no cover - 依赖未安装时降级
    ChatOpenAI = None  # type: ignore
    OpenAIEmbeddings = None  # type: ignore
    HumanMessage = None  # type: ignore
    SystemMessage = None  # type: ignore
    print(f"[LLM] LangChain 不可用，降级为确定性逻辑: {exc}", file=sys.stderr)


class LLMClient:
    def __init__(self) -> None:
        self._chat = None
        self._key = None
        self._embeddings = None

    @property
    def available(self) -> bool:
        return bool(settings.llm_ready and ChatOpenAI is not None)

    def invalidate(self) -> None:
        self._chat = None
        self._key = None
        self._embeddings = None

    def _chat_model(self):
        if not self.available:
            return None
        key = (settings.api_key, settings.base_url, settings.model_name, settings.temperature, settings.max_tokens)
        if self._chat is None or self._key != key:
            self._chat = ChatOpenAI(
                api_key=settings.api_key,
                base_url=settings.base_url,
                model=settings.model_name,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                timeout=settings.request_timeout,
                max_retries=1,
            )
            self._key = key
        return self._chat

    def embeddings(self):
        if not settings.llm_ready or OpenAIEmbeddings is None:
            return None
        if self._embeddings is None:
            self._embeddings = OpenAIEmbeddings(
                model=settings.embedding_model,
                api_key=settings.api_key,
                base_url=settings.base_url,
                dimensions=1024,
                check_embedding_ctx_length=False,
            )
        return self._embeddings

    async def chat(
        self,
        system: str,
        user: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        image_base64: Optional[str] = None,
        mime: str = "image/png",
    ) -> Optional[str]:
        model = self._chat_model()
        if model is None:
            return None
        content = user
        if image_base64:
            content = [
                {"type": "text", "text": user},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_base64}"}},
            ]
        messages = [SystemMessage(content=system), HumanMessage(content=content)]
        try:
            response = await model.ainvoke(
                messages,
                temperature=settings.temperature if temperature is None else temperature,
                max_tokens=max_tokens or settings.max_tokens,
            )
            raw = response.content
            if isinstance(raw, list):
                raw = "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in raw)
            return str(raw or "").strip() or None
        except Exception as exc:
            print(f"[LLM] 调用失败: {exc}", file=sys.stderr)
            return None

    async def chat_json(
        self,
        system: str,
        user: str,
        schema: Type[BaseModel],
        temperature: Optional[float] = None,
        image_base64: Optional[str] = None,
        mime: str = "image/png",
    ) -> Optional[BaseModel]:
        schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)[:3500]
        prompt = (
            f"{user}\n\n请只输出一个 JSON 对象，必须符合以下 JSON Schema：\n{schema_hint}\n"
            "不要输出 Markdown 代码块、解释或额外文字。"
        )
        raw = await self.chat(system, prompt, temperature=temperature, image_base64=image_base64, mime=mime)
        if not raw:
            return None
        data = extract_json(raw)
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            repair = (
                f"你上一次输出的 JSON 不符合 Schema，错误如下：\n{exc}\n"
                f"上一次输出：\n{raw[:2000]}\n"
                f"目标 Schema：\n{schema_hint}\n请修正后只输出合法 JSON。"
            )
            raw2 = await self.chat("你是严谨的 JSON 修复器。", repair, temperature=0.1)
            data2 = extract_json(raw2 or "")
            try:
                return schema.model_validate(data2)
            except Exception:
                print(f"[LLM] JSON 修复失败: {exc}", file=sys.stderr)
                return None


llm = LLMClient()
