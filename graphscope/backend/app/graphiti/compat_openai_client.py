"""
兼容的 OpenAI 客户端

Graphiti 默认的 OpenAIClient 使用 OpenAI Responses API (client.responses.parse)，
但很多第三方 LLM 代理（如 one-api）只支持传统的 Chat Completions API。

本模块提供 CompatOpenAIClient，将所有调用都路由到 Chat Completions API，
并使用 json_schema 硬约束（constrained decoding）确保输出 100% 符合格式。
"""

import json
import logging
import typing

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from graphiti_core.llm_client.config import DEFAULT_MAX_TOKENS, LLMConfig
from graphiti_core.llm_client.openai_base_client import (
    DEFAULT_REASONING,
    DEFAULT_VERBOSITY,
    BaseOpenAIClient,
)

logger = logging.getLogger(__name__)


class CompatOpenAIClient(BaseOpenAIClient):
    """
    兼容的 OpenAI 客户端（json_schema 硬约束版）。

    与 Graphiti 默认的 OpenAIClient 相比：
    - 使用 chat.completions.create + response_format=json_schema（硬约束）
      而非 responses.parse (Responses API)
    - 效果等价：都是服务端 constrained decoding，100% 格式正确
    - 兼容不支持 Responses API 但支持 json_schema 的第三方 LLM 代理
    """

    def __init__(
        self,
        config: LLMConfig | None = None,
        cache: bool = False,
        client: typing.Any = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        reasoning: str = DEFAULT_REASONING,
        verbosity: str = DEFAULT_VERBOSITY,
    ):
        super().__init__(config, cache, max_tokens, reasoning, verbosity)

        if config is None:
            config = LLMConfig()

        if client is None:
            self.client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
        else:
            self.client = client

    def _pydantic_to_strict_schema(self, response_model: type[BaseModel]) -> dict:
        """将 Pydantic model 转换为 OpenAI json_schema 格式的严格 schema。"""
        raw_schema = response_model.model_json_schema()
        strict_schema = self._make_strict(raw_schema)
        return strict_schema

    def _make_strict(self, schema: dict) -> dict:
        """递归地将 JSON Schema 转换为 strict 模式。"""
        schema = dict(schema)

        if "$defs" in schema:
            schema["$defs"] = {
                name: self._make_strict(defn)
                for name, defn in schema["$defs"].items()
            }

        if "anyOf" in schema:
            schema["anyOf"] = [self._make_strict(opt) for opt in schema["anyOf"]]
            return schema

        if "$ref" in schema:
            return schema

        schema_type = schema.get("type")

        if schema_type == "object":
            schema["additionalProperties"] = False
            properties = schema.get("properties", {})
            if properties:
                schema["required"] = list(properties.keys())
                schema["properties"] = {
                    name: self._make_strict(prop)
                    for name, prop in properties.items()
                }

        elif schema_type == "array":
            if "items" in schema:
                schema["items"] = self._make_strict(schema["items"])

        schema.pop("title", None)
        schema.pop("default", None)

        return schema

    async def _create_structured_completion(
        self,
        model: str,
        messages: list[ChatCompletionMessageParam],
        temperature: float | None,
        max_tokens: int,
        response_model: type[BaseModel],
        reasoning: str | None = None,
        verbosity: str | None = None,
    ):
        """使用 Chat Completions API + json_schema 硬约束。"""
        logger.info(
            f"CompatOpenAIClient._create_structured_completion called for "
            f"model={model}, response_model={response_model.__name__}"
        )

        strict_schema = self._pydantic_to_strict_schema(response_model)

        is_reasoning_model = (
            model.startswith("gpt-5")
            or model.startswith("o1")
            or model.startswith("o3")
        )

        request_kwargs: dict[str, typing.Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": strict_schema,
                },
            },
        }

        temperature_value = temperature if not is_reasoning_model else None
        if temperature_value is not None:
            request_kwargs["temperature"] = temperature_value

        response = await self.client.chat.completions.create(**request_kwargs)

        return response

    async def _create_completion(
        self,
        model: str,
        messages: list[ChatCompletionMessageParam],
        temperature: float | None,
        max_tokens: int,
        response_model: type[BaseModel] | None = None,
        reasoning: str | None = None,
        verbosity: str | None = None,
    ):
        """Create a regular completion with JSON format."""
        is_reasoning_model = (
            model.startswith("gpt-5")
            or model.startswith("o1")
            or model.startswith("o3")
        )

        return await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature if not is_reasoning_model else None,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

    def _handle_structured_response(self, response: typing.Any) -> tuple[dict[str, typing.Any], int, int]:
        """处理 Chat Completions API 的结构化响应。"""
        return self._handle_json_response(response)
