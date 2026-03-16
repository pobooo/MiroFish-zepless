"""
兼容的 OpenAI 客户端

Graphiti 默认的 OpenAIClient 使用 OpenAI Responses API (client.responses.parse)，
但很多第三方 LLM 代理（如 one-api）只支持传统的 Chat Completions API。

本模块提供 CompatOpenAIClient，将所有调用都路由到 Chat Completions API，
保持与 Graphiti 的完全兼容。
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
    兼容的 OpenAI 客户端。

    与 Graphiti 默认的 OpenAIClient 相比，主要差异：
    - _create_structured_completion: 使用 chat.completions.create + JSON mode
      而非 responses.parse (Responses API)
    - 完全兼容不支持 Responses API 的第三方 LLM 代理
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

    def _build_schema_instruction(self, response_model: type[BaseModel]) -> str:
        """
        根据 Pydantic model 构建清晰的 JSON 输出指令。
        
        直接生成完整的 JSON 示例，使 LLM 精确理解期望的输出格式。
        """
        schema = response_model.model_json_schema()
        defs = schema.get("$defs", {})

        # 递归构建完整的示例对象
        example_obj = self._build_example_from_schema(schema, defs)
        example_str = json.dumps(example_obj, ensure_ascii=False, indent=2)

        instruction = (
            f"\n\n[OUTPUT FORMAT REQUIREMENT]\n"
            f"You MUST respond with a JSON object in EXACTLY this format:\n"
            f"```\n{example_str}\n```\n"
            f"CRITICAL RULES:\n"
            f"1. Your response must be a valid JSON object with the EXACT same keys as shown above.\n"
            f"2. Fill in actual extracted data values - DO NOT return the schema/format itself.\n"
            f"3. DO NOT use NER-style output (no 'content', 'pos', 'label' fields).\n"
            f"4. DO NOT wrap in markdown code blocks.\n"
            f"5. Output ONLY the JSON object.\n"
        )

        return instruction

    def _build_example_from_schema(self, schema: dict, defs: dict) -> dict | list | str | int | float | bool | None:
        """递归从 JSON Schema 构建一个完整的示例对象。"""
        # 处理 $ref 引用
        if "$ref" in schema:
            ref_path = schema["$ref"]  # e.g. "#/$defs/ExtractedEntity"
            ref_name = ref_path.split("/")[-1]
            if ref_name in defs:
                return self._build_example_from_schema(defs[ref_name], defs)
            return {}

        schema_type = schema.get("type", "object")

        if schema_type == "object":
            properties = schema.get("properties", {})
            result = {}
            for prop_name, prop_info in properties.items():
                result[prop_name] = self._build_example_value(prop_name, prop_info, defs)
            return result
        elif schema_type == "array":
            items = schema.get("items", {})
            item_example = self._build_example_from_schema(items, defs)
            return [item_example]
        elif schema_type == "string":
            return "example_value"
        elif schema_type == "integer":
            return 0
        elif schema_type == "number":
            return 0.0
        elif schema_type == "boolean":
            return False
        else:
            return None

    def _build_example_value(self, field_name: str, field_info: dict, defs: dict):
        """为单个字段构建示例值。"""
        # 处理 $ref
        if "$ref" in field_info:
            return self._build_example_from_schema(field_info, defs)

        # 处理 anyOf (Optional 字段)
        if "anyOf" in field_info:
            for option in field_info["anyOf"]:
                if option.get("type") != "null":
                    return self._build_example_value(field_name, option, defs)
            return None

        field_type = field_info.get("type", "string")
        description = field_info.get("description", "")

        if field_type == "array":
            items = field_info.get("items", {})
            item_example = self._build_example_from_schema(items, defs)
            return [item_example]
        elif field_type == "integer":
            return 1
        elif field_type == "number":
            return 1.0
        elif field_type == "boolean":
            return False
        elif field_type == "string":
            # 根据字段名和描述给出更有意义的示例
            if "name" in field_name.lower():
                return "Entity Name"
            elif "type" in field_name.lower():
                return "TYPE_NAME"
            elif "fact" in field_name.lower() or "description" in field_name.lower():
                return "A description of the relationship or entity"
            elif "date" in field_name.lower() or "time" in field_name.lower() or "_at" in field_name.lower():
                return "2026-01-01T00:00:00Z"
            elif "summary" in field_name.lower():
                return "A brief summary"
            else:
                return "value"
        elif field_type == "object":
            return {}
        else:
            return None

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
        使用 Chat Completions API + JSON mode 替代 Responses API。

        通过在 system prompt 中注入字段描述和示例来引导模型输出结构化数据，
        而非使用 OpenAI 的 responses.parse 端点。
        """
        logger.info(f"CompatOpenAIClient._create_structured_completion called for model={model}, response_model={response_model.__name__}")

        # 构建清晰的输出指令（不使用 raw JSON Schema，避免 LLM 原样返回 schema）
        schema_instruction = self._build_schema_instruction(response_model)

        # 构建带 schema 提示的消息列表
        augmented_messages = list(messages)

        # 找到最后一条 user 消息并追加指令
        for i in range(len(augmented_messages) - 1, -1, -1):
            msg = augmented_messages[i]
            if msg.get("role") == "user":
                augmented_messages[i] = {
                    "role": "user",
                    "content": msg["content"] + schema_instruction,
                }
                break

        is_reasoning_model = (
            model.startswith("gpt-5")
            or model.startswith("o1")
            or model.startswith("o3")
        )

        request_kwargs: dict[str, typing.Any] = {
            "model": model,
            "messages": augmented_messages,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        temperature_value = temperature if not is_reasoning_model else None
        if temperature_value is not None:
            request_kwargs["temperature"] = temperature_value

        response = await self.client.chat.completions.create(**request_kwargs)

        # 验证并修复响应
        content = response.choices[0].message.content or '{}'
        fixed_content = self._fix_llm_response(content, response_model)
        if fixed_content != content:
            response.choices[0].message.content = fixed_content

        return response

    def _fix_llm_response(self, content: str, response_model: type[BaseModel]) -> str:
        """
        尝试修复 LLM 返回的 JSON，使其符合 response_model 的结构。
        
        处理以下常见问题：
        1. LLM 返回 JSON Schema 本身而非数据
        2. LLM 返回单个对象而非外层包装（如 edge 而非 {"edges": [edge]}）
        3. LLM 返回数组而非外层包装对象（如 [edge1, edge2] 而非 {"edges": [...]})
        """
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for {response_model.__name__}: {e}")
            return content

        # 先尝试直接验证——如果成功则直接返回
        try:
            response_model(**parsed)
            return content
        except Exception:
            pass  # 需要修复

        schema = response_model.model_json_schema()
        properties = schema.get("properties", {})

        # Case 1: LLM 返回了 schema 定义本身
        if "properties" in parsed and "type" in parsed and parsed.get("type") == "object":
            logger.warning(f"LLM returned schema definition instead of data for {response_model.__name__}")
            fixed = self._build_default_instance(response_model)
            logger.info(f"Fixed (schema→default): {json.dumps(fixed, ensure_ascii=False)[:200]}")
            return json.dumps(fixed, ensure_ascii=False)

        # Case 2: 模型期望有一个 list 字段作为外层包装，但 LLM 返回了单个对象或数组
        list_fields = {}
        for field_name, field_info in properties.items():
            if field_info.get("type") == "array":
                list_fields[field_name] = field_info

        if len(list_fields) == 1:
            # 模型只有一个 list 字段——最常见的情况（如 ExtractedEdges.edges, ExtractedEntities.extracted_entities）
            list_field_name = list(list_fields.keys())[0]
            
            if list_field_name not in parsed:
                # LLM 没有返回外层包装
                if isinstance(parsed, list):
                    # Case 2a: LLM 直接返回了数组
                    fixed = {list_field_name: parsed}
                    logger.info(f"Fixed (array→wrapped): added '{list_field_name}' wrapper")
                    return json.dumps(fixed, ensure_ascii=False)
                elif isinstance(parsed, dict):
                    # Case 2b: LLM 返回了单个对象，应该包装成数组
                    items_ref = list_fields[list_field_name].get("items", {})
                    # 检查 parsed 是否看起来像单个 item
                    if items_ref.get("$ref") or items_ref.get("type") == "object":
                        fixed = {list_field_name: [parsed]}
                        logger.info(f"Fixed (single→wrapped array): added '{list_field_name}' wrapper with single item")
                        # 验证修复后的结构
                        try:
                            response_model(**fixed)
                            return json.dumps(fixed, ensure_ascii=False)
                        except Exception:
                            pass  # 修复失败，继续尝试其他方式

        # Case 3: 数组内元素格式不对（如 NER 格式 → Graphiti 格式）或缺少必需字段
        if isinstance(parsed, dict) and len(list_fields) == 1:
            list_field_name = list(list_fields.keys())[0]
            if list_field_name in parsed and isinstance(parsed[list_field_name], list):
                items = parsed[list_field_name]
                if items and isinstance(items[0], dict):
                    # 获取目标元素的 schema
                    items_schema = list_fields[list_field_name].get("items", {})
                    defs = schema.get("$defs", {})
                    
                    # 解析 $ref 获取目标字段
                    target_props = {}
                    target_required = []
                    if "$ref" in items_schema:
                        ref_name = items_schema["$ref"].split("/")[-1]
                        if ref_name in defs:
                            target_props = defs[ref_name].get("properties", {})
                            target_required = defs[ref_name].get("required", [])
                    elif "properties" in items_schema:
                        target_props = items_schema["properties"]
                        target_required = items_schema.get("required", [])
                    
                    if target_props:
                        target_fields = set(target_props.keys())
                        actual_fields = set(items[0].keys())
                        
                        if not target_fields.issubset(actual_fields):
                            # Case 3a: 字段名完全不匹配（如 NER 格式），尝试映射
                            mapped_items = []
                            for item in items:
                                mapped = self._map_item_fields(item, target_props)
                                if mapped:
                                    mapped_items.append(mapped)
                            
                            if mapped_items:
                                fixed = dict(parsed)
                                fixed[list_field_name] = mapped_items
                                try:
                                    response_model(**fixed)
                                    logger.info(f"Fixed (mapped {len(mapped_items)} items in '{list_field_name}')")
                                    return json.dumps(fixed, ensure_ascii=False)
                                except Exception as e:
                                    logger.warning(f"Item mapping validation failed: {e}")
                        
                        # Case 3b: 个别元素缺少某些必需字段，或字段值为 None 但需要非 None 类型，补充默认值
                        fixed_items = []
                        any_fixed = False
                        for item in items:
                            if not isinstance(item, dict):
                                fixed_items.append(item)
                                continue
                            fixed_item = dict(item)
                            for req_field in target_required:
                                field_schema = target_props.get(req_field, {})
                                # 判断字段是否允许 None
                                field_nullable = False
                                if "anyOf" in field_schema:
                                    field_nullable = any(
                                        opt.get("type") == "null" for opt in field_schema["anyOf"]
                                    )
                                
                                needs_fix = False
                                if req_field not in fixed_item:
                                    # 字段完全缺失
                                    needs_fix = True
                                elif fixed_item[req_field] is None and not field_nullable:
                                    # 字段值为 None 但字段不允许 null
                                    needs_fix = True
                                
                                if needs_fix:
                                    default_val = self._infer_missing_field(req_field, field_schema, fixed_item)
                                    fixed_item[req_field] = default_val
                                    any_fixed = True
                            fixed_items.append(fixed_item)
                        
                        if any_fixed:
                            # 过滤掉"太多核心字段为 None/缺失"的无效条目
                            # 如果一个 item 的多数必需字段都需要填充默认值，说明 LLM 返回了一个空壳，应该丢弃
                            valid_items = []
                            for idx, item in enumerate(fixed_items):
                                if not isinstance(item, dict):
                                    valid_items.append(item)
                                    continue
                                original_item = items[idx] if idx < len(items) else {}
                                none_count = sum(
                                    1 for rf in target_required
                                    if (not isinstance(original_item, dict)) or
                                       rf not in original_item or original_item[rf] is None
                                )
                                if none_count >= len(target_required) * 0.5 and none_count >= 2:
                                    logger.info(f"Dropping invalid item {idx}: {none_count}/{len(target_required)} required fields were null/missing")
                                    continue
                                valid_items.append(item)
                            
                            fixed = dict(parsed)
                            fixed[list_field_name] = valid_items
                            try:
                                response_model(**fixed)
                                dropped = len(fixed_items) - len(valid_items)
                                msg = f"Fixed (filled missing fields in '{list_field_name}'"
                                if dropped > 0:
                                    msg += f", dropped {dropped} invalid items"
                                msg += ")"
                                logger.info(msg)
                                return json.dumps(fixed, ensure_ascii=False)
                            except Exception as e:
                                logger.warning(f"Fill missing fields validation failed: {e}")

        # Case 4: 模型期望多个非 list 字段，但 LLM 遗漏了某些字段
        # 尝试填充缺失字段的默认值
        missing_required = []
        for field_name in schema.get("required", []):
            if field_name not in parsed:
                missing_required.append(field_name)
        
        if missing_required and isinstance(parsed, dict):
            fixed = dict(parsed)
            for field_name in missing_required:
                field_info = properties.get(field_name, {})
                field_type = field_info.get("type", "string")
                if field_type == "array":
                    fixed[field_name] = []
                elif field_type == "integer":
                    fixed[field_name] = 0
                elif field_type == "number":
                    fixed[field_name] = 0.0
                elif field_type == "boolean":
                    fixed[field_name] = False
                elif field_type == "string":
                    fixed[field_name] = ""
                else:
                    fixed[field_name] = None
            
            try:
                response_model(**fixed)
                logger.info(f"Fixed (added missing fields {missing_required})")
                return json.dumps(fixed, ensure_ascii=False)
            except Exception:
                pass

        logger.warning(f"Could not fix LLM response for {response_model.__name__}, returning original")
        return content

    def _build_default_instance(self, response_model: type[BaseModel]) -> dict:
        """为一个 Pydantic model 构建默认值实例。"""
        result = {}
        for field_name, field_info in response_model.model_fields.items():
            if field_info.default is not None:
                result[field_name] = field_info.default
            else:
                annotation = field_info.annotation
                annotation_str = str(annotation)
                if annotation == list or "list[" in annotation_str.lower():
                    result[field_name] = []
                elif annotation == int:
                    result[field_name] = 0
                elif annotation == float:
                    result[field_name] = 0.0
                elif annotation == bool:
                    result[field_name] = False
                elif annotation == str:
                    result[field_name] = ""
                else:
                    result[field_name] = None
        return result

    def _infer_missing_field(self, field_name: str, field_schema: dict, item: dict) -> str | int | float | bool | None:
        """
        为缺失的必需字段推断一个合理的默认值。
        
        对于某些字段，可以从已有数据中推断出有意义的值。
        """
        # 处理 anyOf (Optional 字段)
        if "anyOf" in field_schema:
            for option in field_schema["anyOf"]:
                if option.get("type") == "null":
                    return None
            # 非 nullable，取第一个非 null 类型
            for option in field_schema["anyOf"]:
                if option.get("type") != "null":
                    field_schema = option
                    break

        field_type = field_schema.get("type", "string")
        
        if field_type == "string":
            # 针对 relation_type 的特殊处理：从 fact 或其他字段推断
            if field_name == "relation_type":
                # 尝试从 fact 字段生成 relation_type
                fact = item.get("fact", "")
                if fact:
                    # 提取关键动词/关系词作为 relation_type
                    return "RELATED_TO"
                return "RELATED_TO"
            elif "name" in field_name:
                return "Unknown"
            elif "type" in field_name:
                return "UNKNOWN_TYPE"
            elif "fact" in field_name or "description" in field_name:
                return item.get("fact", item.get("description", ""))
            else:
                return ""
        elif field_type == "integer":
            return 0
        elif field_type == "number":
            return 0.0
        elif field_type == "boolean":
            return False
        elif field_type == "array":
            return []
        else:
            return None

    def _map_item_fields(self, item: dict, target_props: dict) -> dict | None:
        """
        尝试将 LLM 返回的非标准格式 item 映射到目标格式。
        
        常见映射：
        - NER 格式 {"content": "X", "label": "Y", "pos": [...]} → {"name": "X", "entity_type_id": 0}
        - 其他非标准键名映射
        """
        # 定义常见的字段名映射
        field_mappings = {
            # 目标字段 → 可能的源字段名
            "name": ["content", "text", "entity", "entity_name", "value", "word", "mention"],
            "entity_type_id": ["type_id", "type", "category_id", "class_id"],
            "source_entity_name": ["source", "from", "from_entity", "source_name", "head", "head_entity"],
            "target_entity_name": ["target", "to", "to_entity", "target_name", "tail", "tail_entity"],
            "relation_type": ["relation", "relationship", "type", "edge_type", "predicate", "label"],
            "fact": ["description", "text", "content", "detail", "fact_text"],
            "summary": ["description", "text", "content", "detail"],
        }

        mapped = {}
        for target_field, target_info in target_props.items():
            if target_field in item:
                # 字段名完全匹配
                mapped[target_field] = item[target_field]
            else:
                # 尝试模糊映射
                possible_sources = field_mappings.get(target_field, [])
                found = False
                for source_field in possible_sources:
                    if source_field in item:
                        mapped[target_field] = item[source_field]
                        found = True
                        break
                
                if not found:
                    # 使用默认值
                    target_type = target_info.get("type", "string")
                    if target_type == "integer":
                        mapped[target_field] = 0
                    elif target_type == "string":
                        # 如果目标是 name 且源中有 content/text，使用它
                        if "name" in target_field and ("content" in item or "text" in item):
                            mapped[target_field] = item.get("content", item.get("text", ""))
                        else:
                            mapped[target_field] = ""
                    elif target_type == "array":
                        mapped[target_field] = []
                    elif target_type == "boolean":
                        mapped[target_field] = False
                    else:
                        mapped[target_field] = None

        return mapped if mapped else None

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

        由于我们使用 chat.completions.create 而非 responses.parse，
        响应格式是标准的 ChatCompletion，需要用 _handle_json_response 的方式解析。
        """
        return self._handle_json_response(response)
