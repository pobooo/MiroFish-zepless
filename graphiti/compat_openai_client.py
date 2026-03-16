"""
兼容的 OpenAI 客户端

Graphiti 默认的 OpenAIClient 使用 OpenAI Responses API (client.responses.parse)，
但很多第三方 LLM 代理（如 one-api）只支持传统的 Chat Completions API。

本模块提供 CompatOpenAIClient，将所有调用都路由到 Chat Completions API，
并使用 json_schema 硬约束（constrained decoding）确保输出 100% 符合格式。

升级历史：
- v1: json_object 软约束 + prompt 注入 schema + 后处理修复
- v2 (当前): json_schema 硬约束，服务端 token 级别格式控制，无需 prompt 注入和后处理
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
        """
        将 Pydantic model 转换为 OpenAI json_schema 格式的严格 schema。
        
        OpenAI json_schema 模式要求：
        1. 所有 object 必须有 additionalProperties: false
        2. 所有字段都必须在 required 中列出
        3. Optional 字段使用 anyOf: [{实际类型}, {type: "null"}] 表示
        4. 不能有 $defs 中未使用的定义（但保留也可以）
        """
        raw_schema = response_model.model_json_schema()
        
        # 递归处理 schema，添加 strict 模式所需的约束
        strict_schema = self._make_strict(raw_schema)
        
        return strict_schema

    def _make_strict(self, schema: dict) -> dict:
        """递归地将 JSON Schema 转换为 strict 模式。"""
        schema = dict(schema)  # shallow copy
        
        # 处理 $defs 中的所有定义
        if "$defs" in schema:
            schema["$defs"] = {
                name: self._make_strict(defn)
                for name, defn in schema["$defs"].items()
            }
        
        # 处理 anyOf（Pydantic Optional 字段生成的）
        if "anyOf" in schema:
            schema["anyOf"] = [self._make_strict(opt) for opt in schema["anyOf"]]
            return schema
        
        # 处理 $ref - 不需要修改
        if "$ref" in schema:
            return schema
        
        schema_type = schema.get("type")
        
        if schema_type == "object":
            # 所有 object 必须有 additionalProperties: false
            schema["additionalProperties"] = False
            
            # 所有属性都必须在 required 中
            properties = schema.get("properties", {})
            if properties:
                schema["required"] = list(properties.keys())
                # 递归处理每个属性
                schema["properties"] = {
                    name: self._make_strict(prop)
                    for name, prop in properties.items()
                }
        
        elif schema_type == "array":
            # 递归处理 items
            if "items" in schema:
                schema["items"] = self._make_strict(schema["items"])
        
        # 移除 title 和 default（OpenAI strict 模式不允许 default）
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
        """
        使用 Chat Completions API + json_schema 硬约束。

        服务端使用 constrained decoding 在 token 级别强制输出格式，
        确保 100% 符合 schema，无需任何 prompt 注入或后处理修复。
        """
        logger.info(
            f"CompatOpenAIClient._create_structured_completion called for "
            f"model={model}, response_model={response_model.__name__}"
        )

        # 从 Pydantic model 生成 strict JSON Schema
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
        """
        处理 Chat Completions API 的结构化响应。

        json_schema 硬约束保证输出 100% 符合格式，
        直接解析即可，无需后处理修复。
        """
        return self._handle_json_response(response)
