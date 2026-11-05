"""教师 AI 助手：用 FastMCP Client 调工具，用硅基流动 Qwen 做 function calling。

流程与 backend-example/mcp-agent-service 一致：
拉取 MCP 工具 → 转成 OpenAI tools → 模型选择工具 → 执行 → 结果回填 → 生成中文回答。
"""
from __future__ import annotations

import json
import re
import secrets
import time
import uuid
from typing import Any, Optional

from fastmcp import Client
from openai import AsyncOpenAI

from . import db
from .config import settings
from .mcp_server import DESTRUCTIVE_TOOLS, TOOL_LABELS, WRITE_TOOLS, mcp

MAX_LOOPS = 6
HISTORY_LIMIT = 8
CONFIRM_TTL_MS = 5 * 60 * 1000
TITLE_LIMIT = 20

SYSTEM_PROMPT = """你是 ClassMate AI 课堂助教平台的教师端助手，服务对象是中小学教师。
你可以调用 MCP 工具完成查询与增删改查。规则：
1. 需要 id 的操作，必须先调用查询工具拿到真实 id，禁止编造。
2. 删除类工具由系统负责二次确认，你只需要发起调用，不要编造确认结果。
3. 一次只解决教师当前这句话；信息不足时先用查询工具补齐。
4. 回答用简体中文，简洁分点，不要暴露内部参数、token 或工具实现细节。
5. 工具返回 ok=false 时，如实说明原因并给出下一步建议。
6. 时间、日期、人数、分数等数据必须直接引用工具返回的内容（工具已给出可读时间），不要自行换算或编造。"""

PLAIN_PROMPT = """你是 ClassMate AI 课堂助教平台的教师端助手，用简体中文回答中小学教师的问题。
当前未开启工具模式，不能查询或修改平台数据；需要操作数据时请提示教师打开「MCP 工具模式」。"""


def _clean_history(history: Optional[list[dict]]) -> list[dict]:
    cleaned = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            cleaned.append({"role": role, "content": content})
    return cleaned[-HISTORY_LIMIT:]


def _tool_schema(tool: Any) -> dict:
    raw = None
    if hasattr(tool, "model_dump"):
        try:
            raw = tool.model_dump()
        except Exception:
            raw = None
    if not isinstance(raw, dict):
        raw = {
            "name": getattr(tool, "name", ""),
            "description": getattr(tool, "description", ""),
            "inputSchema": getattr(tool, "inputSchema", None),
        }
    schema = raw.get("inputSchema") or raw.get("parameters") or {"type": "object", "properties": {}}
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    return {
        "type": "function",
        "function": {
            "name": raw.get("name") or getattr(tool, "name", ""),
            "description": (raw.get("description") or "")[:1024],
            "parameters": schema,
        },
    }


def _result_text(result: Any) -> str:
    data = getattr(result, "data", None)
    if isinstance(data, (dict, list)):
        return json.dumps(data, ensure_ascii=False)
    if isinstance(data, str) and data.strip():
        return data
    parts = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _is_ok(text: str) -> bool:
    try:
        payload = json.loads(text)
    except Exception:
        return True
    return bool(payload.get("ok", True))


XML_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def _parse_text_calls(*texts: str) -> list[dict]:
    """兼容不支持原生 tool_calls 的模型：解析 Qwen 输出的 <tool_call>{...}</tool_call>。"""
    calls: list[dict] = []
    for text in texts:
        for blob in XML_CALL_RE.findall(text or ""):
            try:
                payload = json.loads(blob)
            except json.JSONDecodeError:
                continue
            name = payload.get("name") or payload.get("tool")
            arguments = payload.get("arguments") or payload.get("args") or {}
            if name and isinstance(arguments, dict):
                calls.append({"name": name, "arguments": arguments})
    return calls


def _message_text(msg: Any) -> str:
    """部分模型（Qwen3-VL）会把内容写进 reasoning_content，这里统一取出可见文本。"""
    content = (getattr(msg, "content", None) or "").strip()
    if content:
        return content
    return (getattr(msg, "reasoning_content", None) or "").strip()


_PENDING: dict[str, dict[str, Any]] = {}


def _create_confirm(teacher_id: str, name: str, arguments: dict, conversation_id: str) -> dict:
    token = secrets.token_hex(4)
    _PENDING[token] = {
        "teacher_id": teacher_id,
        "name": name,
        "arguments": arguments,
        "conversation_id": conversation_id,
        "expires_at": time.time() * 1000 + CONFIRM_TTL_MS,
    }
    # 清掉过期 token，避免内存无限增长
    for key, item in list(_PENDING.items()):
        if item["expires_at"] < time.time() * 1000:
            _PENDING.pop(key, None)
    return {
        "token": token,
        "tool": name,
        "label": TOOL_LABELS.get(name, name),
        "arguments": arguments,
        "expires_in": CONFIRM_TTL_MS // 1000,
    }


def _take_confirm(token: str, teacher_id: str) -> Optional[dict]:
    item = _PENDING.pop(token, None)
    if not item or item["teacher_id"] != teacher_id:
        return None
    if item["expires_at"] < time.time() * 1000:
        return None
    return item


class AssistantAgent:
    def __init__(self) -> None:
        self._client: Optional[AsyncOpenAI] = None

    # ------------------------------------------------------------ 基础能力

    def llm(self) -> AsyncOpenAI:
        if not self._client:
            self._client = AsyncOpenAI(
                api_key=settings.api_key,
                base_url=settings.base_url,
                timeout=settings.request_timeout,
            )
        return self._client

    def _remember(self, teacher_id: str, conversation_id: str, role: str, content: str, tool_calls: list) -> None:
        now = db.now_ms()
        db.execute(
            "INSERT INTO assistant_messages(id, user_id, conversation_id, role, content, tool_calls, created_at) VALUES(?,?,?,?,?,?,?)",
            (
                f"msg_{uuid.uuid4().hex[:10]}",
                teacher_id,
                conversation_id,
                role,
                content,
                json.dumps(tool_calls, ensure_ascii=False),
                now,
            ),
        )
        db.execute("UPDATE assistant_conversations SET updated_at=? WHERE id=?", (now, conversation_id))

    def _ensure_conversation(self, teacher_id: str, conversation_id: Optional[str], message: str) -> str:
        """没有归属对话就新建；对话不属于当前教师时也新建，避免串号。"""
        if conversation_id:
            row = db.query_one(
                "SELECT id FROM assistant_conversations WHERE id=? AND user_id=?",
                (conversation_id, teacher_id),
            )
            if row:
                return conversation_id
        new_id = f"conv_{uuid.uuid4().hex[:10]}"
        now = db.now_ms()
        title = " ".join(message.split())[:TITLE_LIMIT] or "新的对话"
        db.execute(
            "INSERT INTO assistant_conversations(id, user_id, title, created_at, updated_at) VALUES(?,?,?,?,?)",
            (new_id, teacher_id, title, now, now),
        )
        return new_id

    def _audit(self, teacher_id: str, name: str, arguments: dict, result: str, status: str) -> None:
        db.execute(
            "INSERT INTO mcp_audit_logs(id, user_id, tool, arguments, result, status, created_at) VALUES(?,?,?,?,?,?,?)",
            (
                f"audit_{uuid.uuid4().hex[:10]}",
                teacher_id,
                name,
                json.dumps(arguments, ensure_ascii=False, default=str),
                result[:4000],
                status,
                db.now_ms(),
            ),
        )

    async def _execute(self, client: Client, teacher_id: str, name: str, arguments: dict, traces: list) -> str:
        started = time.time()
        # 教师身份不让模型填，统一由后端注入
        if name in {"list_classrooms", "create_classroom", "close_classroom"}:
            arguments = {**arguments, "teacher_id": teacher_id}
        try:
            result = await client.call_tool(name, arguments)
            text = _result_text(result)
            status = "ok" if _is_ok(text) else "failed"
        except Exception as exc:  # 工具不存在 / 参数校验失败
            text = json.dumps({"ok": False, "message": f"工具执行失败：{exc}"}, ensure_ascii=False)
            status = "failed"
        trace = {
            "tool": name,
            "label": TOOL_LABELS.get(name, name),
            "arguments": arguments,
            "result": text,
            "status": status,
            "duration_ms": int((time.time() - started) * 1000),
            "write": name in WRITE_TOOLS,
            "destructive": name in DESTRUCTIVE_TOOLS,
        }
        traces.append(trace)
        self._audit(teacher_id, name, arguments, text, status)
        return text

    # ------------------------------------------------------------ 对话入口

    async def chat(
        self,
        teacher_id: str,
        message: str,
        history: Optional[list[dict]] = None,
        tools_enabled: bool = True,
        confirm_token: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> dict:
        message = (message or "").strip()
        if not message:
            raise ValueError("请输入一句话再发送")
        history = _clean_history(history)

        # 删除确认是上一轮的延续：沿用原对话，且不重复记录同一条用户消息
        pending = _take_confirm(confirm_token, teacher_id) if confirm_token else None
        if pending:
            conversation_id = pending["conversation_id"]
        else:
            conversation_id = self._ensure_conversation(teacher_id, conversation_id, message)
            self._remember(teacher_id, conversation_id, "user", message, [])

        if not tools_enabled:
            answer = await self._plain_reply(message, history)
            self._remember(teacher_id, conversation_id, "assistant", answer, [])
            return {
                "answer": answer,
                "tool_calls": [],
                "need_confirm": None,
                "mode": "chat",
                "conversation_id": conversation_id,
            }

        if not settings.llm_ready:
            answer, traces = await self._offline_reply(teacher_id, message)
            self._remember(teacher_id, conversation_id, "assistant", answer, traces)
            return {
                "answer": answer,
                "tool_calls": traces,
                "need_confirm": None,
                "mode": "offline",
                "conversation_id": conversation_id,
            }

        async with Client(mcp) as client:
            raw_tools = await client.list_tools()
            openai_tools = [_tool_schema(tool) for tool in raw_tools]
            traces: list[dict] = []

            # 上一条消息发起的删除操作已被教师确认：先执行，再让模型总结
            if pending:
                text = await self._execute(client, teacher_id, pending["name"], pending["arguments"], traces)
                answer = await self._summarize(message, history, traces, text)
                self._remember(teacher_id, conversation_id, "assistant", answer, traces)
                return {
                    "answer": answer,
                    "tool_calls": traces,
                    "need_confirm": None,
                    "mode": "tools",
                    "conversation_id": conversation_id,
                }

            messages: list[dict] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *history,
                {"role": "user", "content": message},
            ]
            answer = ""
            for _ in range(MAX_LOOPS):
                completion = await self.llm().chat.completions.create(
                    model=settings.model_name,
                    messages=messages,
                    tools=openai_tools,
                    temperature=settings.temperature,
                    max_tokens=settings.max_tokens,
                )
                msg = completion.choices[0].message
                native = list(msg.tool_calls or [])
                raw = _message_text(msg)
                text_calls = [] if native else _parse_text_calls(raw)

                if not native and not text_calls:
                    answer = raw
                    break

                if native:
                    # 标准 OpenAI function calling：assistant 带 tool_calls，结果用 role=tool 回填
                    messages.append(
                        {
                            "role": "assistant",
                            "content": msg.content or "",
                            "tool_calls": [call.model_dump() for call in msg.tool_calls],
                        }
                    )
                    pending_calls = []
                    for call in native:
                        try:
                            arguments = json.loads(call.function.arguments or "{}")
                        except json.JSONDecodeError:
                            arguments = {}
                        pending_calls.append((call.function.name, arguments, call.id))
                else:
                    # Qwen3-VL 等模型把工具意图写在 <tool_call> 文本里，这里按文本协议执行
                    messages.append({"role": "assistant", "content": raw})
                    pending_calls = [(call["name"], call["arguments"], None) for call in text_calls]

                for name, arguments, call_id in pending_calls:
                    if name in DESTRUCTIVE_TOOLS:
                        confirm = _create_confirm(teacher_id, name, arguments, conversation_id)
                        self._remember(teacher_id, conversation_id, "assistant", f"等待教师确认执行 {name}", [])
                        return {
                            "answer": f"即将执行「{TOOL_LABELS.get(name, name)}」。请你确认后再继续。",
                            "tool_calls": traces,
                            "need_confirm": confirm,
                            "mode": "tools",
                            "conversation_id": conversation_id,
                        }
                    text = await self._execute(client, teacher_id, name, arguments, traces)
                    if call_id:
                        messages.append({"role": "tool", "tool_call_id": call_id, "content": text})
                    else:
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"工具 {name} 的执行结果：\n{text}\n\n"
                                    "请用简体中文向教师汇报结果，不要输出 <tool_call> 标签。"
                                ),
                            }
                        )

            if not answer:
                answer = "工具已执行完成，但模型没有生成总结。请稍后重试或换一种说法。"
            self._remember(teacher_id, conversation_id, "assistant", answer, traces)
            return {
                "answer": answer,
                "tool_calls": traces,
                "need_confirm": None,
                "mode": "tools",
                "conversation_id": conversation_id,
            }

    async def _plain_reply(self, message: str, history: list[dict]) -> str:
        completion = await self.llm().chat.completions.create(
            model=settings.model_name,
            messages=[{"role": "system", "content": PLAIN_PROMPT}, *history, {"role": "user", "content": message}],
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )
        return _message_text(completion.choices[0].message) or "我没有理解你的问题，请换一种说法。"

    async def _summarize(self, message: str, history: list[dict], traces: list[dict], result: str) -> str:
        prompt = (
            f"教师请求：{message}\n"
            f"系统已执行工具：{traces[-1]['tool']}，参数：{json.dumps(traces[-1]['arguments'], ensure_ascii=False)}\n"
            f"工具返回：{result[:1500]}\n"
            "请用简体中文向教师汇报执行结果，并说明下一步可以做什么。"
        )
        completion = await self.llm().chat.completions.create(
            model=settings.model_name,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": prompt}],
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )
        return _message_text(completion.choices[0].message) or "操作已完成。"

    async def _offline_reply(self, teacher_id: str, message: str) -> tuple[str, list[dict]]:
        """离线模式：不做自然语言理解，按关键词直接调查询工具，保证断网也能演示。"""
        traces: list[dict] = []
        async with Client(mcp) as client:
            if any(word in message for word in ("课件", "PPT", "ppt")):
                name, arguments = "list_lessons", {}
            elif any(word in message for word in ("课堂", "班级", "课堂码")):
                name, arguments = "list_classrooms", {"teacher_id": teacher_id}
            elif any(word in message for word in ("题", "题库", "真题")):
                name, arguments = "list_exam_items", {"limit": 10}
            elif any(word in message for word in ("学情", "诊断", "报告")):
                latest = db.query_one(
                    "SELECT id FROM classroom_sessions WHERE teacher_id=? ORDER BY created_at DESC LIMIT 1",
                    (teacher_id,),
                )
                if not latest:
                    return "离线模式下还没有课堂，无法生成学情诊断。", traces
                name, arguments = "get_class_report", {"session_id": latest["id"]}
            else:
                return (
                    "当前是离线演示模式（未配置 api_key），我只能按关键词查询课件、课堂、题目和学情。"
                    "配置模型后可自由对话并执行增删改查。",
                    traces,
                )
            text = await self._execute(client, teacher_id, name, arguments, traces)
        return f"离线模式已执行「{TOOL_LABELS.get(name, name)}」，结果如下：\n{text}", traces


assistant_agent = AssistantAgent()


async def list_tool_meta() -> list[dict]:
    """返回工具清单，供前端展示与调试。"""
    async with Client(mcp) as client:
        tools = await client.list_tools()
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "label": TOOL_LABELS.get(tool.name, tool.name),
            "write": tool.name in WRITE_TOOLS,
            "destructive": tool.name in DESTRUCTIVE_TOOLS,
        }
        for tool in tools
    ]
