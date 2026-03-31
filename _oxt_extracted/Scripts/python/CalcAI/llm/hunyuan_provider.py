"""腾讯混元（Hunyuan）云端模型提供方。

整体思路（为什么这样做）：
- 这个扩展的“自动改单元格/改样式”依赖 OpenAI 风格的 tools/function-calling。
- 腾讯混元提供 OpenAI 兼容的 `/v1/chat/completions`，并支持 `tools` 与返回 `tool_calls`。
- 因此这里做一个“最小适配层”：把 Settings 里的 api_key/base_url/model 读出来，
  以 OpenAI 兼容格式发请求，再把响应解析成应用统一的字典结构：
  {"content": ..., "tool_calls": ..., "usage": ..., "finish_reason": ...}

注意：
- 先按“流式优先”接入（SSE：data: {...}），以便复用现有 UI 的 stream 管线。
- 为了提高兼容性与稳定性：当传了 tools 时默认使用 tool_choice="auto"，
  不强行要求必须 tool（避免不同模型/版本对强制策略支持不一致）。
"""

from __future__ import annotations

import json
import logging
from typing import Generator

import httpx

from config.settings import Settings
from .base_provider import BaseLLMProvider

logger = logging.getLogger(__name__)


class HunyuanProvider(BaseLLMProvider):
    """腾讯混元 OpenAI 兼容接口提供方。"""

    def __init__(self):
        # 为什么在 __init__ 里读取：Settings 统一管理用户配置与持久化，UI 保存后下次启动即可生效。
        s = Settings()
        self._api_key = (s.get("hunyuan_api_key", "") or "").strip()
        self._base_url = (s.get("hunyuan_base_url", "https://api.hunyuan.cloud.tencent.com/v1") or "").rstrip("/")
        self._model = (s.get("hunyuan_default_model", "hunyuan-turbos-latest") or "").strip()

        self._temperature = s.temperature
        self._max_tokens = s.max_tokens

        # 为什么用较长 timeout：工具调用往往多轮、且表格上下文较大，云端响应可能更慢。
        self._client = httpx.Client(timeout=90.0)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, messages: list[dict], tools: list[dict] | None = None, stream: bool = False) -> dict:
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "stream": stream,
            # 说明：混元参数整体兼容 OpenAI，这里沿用通用字段。若某模型忽略也不影响。
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        if tools:
            payload["tools"] = tools
            # 稳定优先：不强制 required/custom，先让模型自主选择，减少“参数不兼容”带来的失败。
            payload["tool_choice"] = "auto"

        return payload

    @staticmethod
    def _parse_response(data: dict) -> dict:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return {
            "content": message.get("content"),
            "tool_calls": message.get("tool_calls"),
            "usage": data.get("usage", {}),
            "finish_reason": choice.get("finish_reason"),
        }

    def chat_completion(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """非流式调用（当前不作为主路径，但保持实现完整，便于后续切换稳定模式）。"""
        if not self._api_key:
            raise PermissionError("腾讯混元 API Key 未设置（hunyuan_api_key）")

        payload = self._build_payload(messages, tools=tools, stream=False)
        try:
            resp = self._client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
        except httpx.ConnectError as exc:
            raise ConnectionError(f"无法连接腾讯混元：{exc}") from exc
        except httpx.TimeoutException as exc:
            raise ConnectionError(f"腾讯混元请求超时：{exc}") from exc

        if resp.status_code != 200:
            # 为什么保留原文：云端错误信息对定位权限/配额/参数问题很关键。
            raise RuntimeError(f"腾讯混元 API 错误（{resp.status_code}）：{resp.text}")

        return self._parse_response(resp.json())

    def stream_completion(self, messages: list[dict], tools: list[dict] | None = None) -> Generator[dict, None, None]:
        """流式调用（SSE），逐块产出 content/tool_calls。

        上层 UI 期望每个 chunk 形如：
        - {"content": "...", "tool_calls": [...], "done": False/True}
        """
        if not self._api_key:
            raise PermissionError("腾讯混元 API Key 未设置（hunyuan_api_key）")

        payload = self._build_payload(messages, tools=tools, stream=True)

        try:
            with self._client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    resp.read()
                    raise RuntimeError(f"腾讯混元 API 错误（{resp.status_code}）：{resp.text}")

                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[len("data: ") :].strip()
                    if not data_str:
                        continue

                    if data_str == "[DONE]":
                        yield {"content": None, "tool_calls": None, "done": True}
                        return

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        # 为什么忽略：SSE 中偶发非 JSON 行不应中断会话（例如服务端日志/空行）。
                        logger.warning("混元 SSE JSON 解析失败：%s", data_str)
                        continue

                    choice = (data.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    finish_reason = choice.get("finish_reason")

                    yield {
                        "content": delta.get("content"),
                        "tool_calls": delta.get("tool_calls"),
                        "done": finish_reason is not None,
                    }

        except httpx.ConnectError as exc:
            raise ConnectionError(f"无法连接腾讯混元：{exc}") from exc
        except httpx.TimeoutException as exc:
            raise ConnectionError(f"腾讯混元请求超时：{exc}") from exc

    def get_available_models(self) -> list[str]:
        """返回缓存/默认模型列表。

        为什么不在线拉取：混元的“列模型接口”不一定稳定开放/权限不一；
        自用场景下，手动填 model id 最可靠。后续需要再扩展。
        """
        return [
            "hunyuan-turbos-latest",
            "hunyuan-functioncall",
        ]

    def set_model(self, model_name: str) -> None:
        self._model = (model_name or "").strip()
        logger.info("腾讯混元模型已切换：%s", self._model)

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

