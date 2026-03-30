"""
Graphiti 客户端工厂（单例模式）

统一管理 Graphiti 的初始化和配置，提供全局单例。
使用 GRAPHSCOPE_ 前缀的环境变量，与 GraphScope 配置风格一致。

使用方式:
    from app.graphiti.graphiti_client import get_graphiti_client
    graphiti = await get_graphiti_client()
"""

import os
import logging
from typing import Optional

from graphiti_core import Graphiti
from graphiti_core.llm_client import LLMConfig

from .compat_openai_client import CompatOpenAIClient
from .local_embedder import LocalEmbedder
from .local_cross_encoder import LocalCrossEncoder

logger = logging.getLogger(__name__)

# 全局单例
_client: Optional[Graphiti] = None

# 支持 Responses API 的 API 端点
_RESPONSES_API_HOSTS = [
    "api.openai.com",
    "azure.openai.com",
]


def _use_responses_api(base_url: str) -> bool:
    """判断 API 端点是否支持 OpenAI Responses API。"""
    force_structured = os.getenv("GRAPHSCOPE_LLM_USE_STRUCTURED_OUTPUT", "").lower()
    if force_structured == "true":
        return True
    if force_structured == "false":
        return False
    base_url_lower = base_url.lower()
    return any(host in base_url_lower for host in _RESPONSES_API_HOSTS)


def _create_llm_client(llm_config: LLMConfig):
    """根据 API 端点自动选择合适的 LLM 客户端。"""
    base_url = llm_config.base_url or ""

    if _use_responses_api(base_url):
        from graphiti_core.llm_client import OpenAIClient
        client = OpenAIClient(config=llm_config)
        logger.info(
            f"LLM 客户端: OpenAIClient (Responses API), "
            f"base_url={base_url}, model={llm_config.model}"
        )
    else:
        client = CompatOpenAIClient(config=llm_config)
        logger.info(
            f"LLM 客户端: CompatOpenAIClient (json_schema), "
            f"base_url={base_url}, model={llm_config.model}"
        )

    return client


def _get_neo4j_config() -> tuple[str, str, str]:
    """读取 Neo4j 配置。"""
    neo4j_uri = os.getenv("GRAPHSCOPE_NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("GRAPHSCOPE_NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("GRAPHSCOPE_NEO4J_PASSWORD", "")

    if not neo4j_password:
        raise ValueError("GRAPHSCOPE_NEO4J_PASSWORD 环境变量未设置")

    return neo4j_uri, neo4j_user, neo4j_password


def _get_llm_config() -> LLMConfig:
    """读取 LLM 配置。"""
    llm_api_key = os.getenv("GRAPHSCOPE_LLM_API_KEY", "")
    llm_base_url = os.getenv("GRAPHSCOPE_LLM_BASE_URL", "")
    llm_model = os.getenv("GRAPHSCOPE_LLM_MODEL_NAME", "gpt-4o-mini")

    if not llm_api_key:
        raise ValueError("GRAPHSCOPE_LLM_API_KEY 环境变量未设置")

    return LLMConfig(
        api_key=llm_api_key,
        base_url=llm_base_url,
        model=llm_model,
        small_model=llm_model,
    )


async def get_graphiti_client() -> Graphiti:
    """获取 Graphiti 客户端单例。"""
    global _client

    if _client is not None:
        return _client

    neo4j_uri, neo4j_user, neo4j_password = _get_neo4j_config()
    llm_config = _get_llm_config()
    llm_client = _create_llm_client(llm_config)

    embedder = LocalEmbedder()
    cross_encoder = LocalCrossEncoder()

    logger.info(f"初始化 Graphiti 客户端: {neo4j_uri}")

    _client = Graphiti(
        neo4j_uri,
        neo4j_user,
        neo4j_password,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
    )

    await _client.build_indices_and_constraints()
    logger.info("Graphiti 客户端初始化完成")

    return _client


async def create_graphiti_client() -> Graphiti:
    """创建新的 Graphiti 客户端实例（非单例，调用方负责 close）。"""
    neo4j_uri, neo4j_user, neo4j_password = _get_neo4j_config()
    llm_config = _get_llm_config()
    llm_client = _create_llm_client(llm_config)

    embedder = LocalEmbedder()
    cross_encoder = LocalCrossEncoder()

    logger.info(f"创建新的 Graphiti 客户端实例: {neo4j_uri}")

    client = Graphiti(
        neo4j_uri,
        neo4j_user,
        neo4j_password,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
    )

    await client.build_indices_and_constraints()
    logger.info("新 Graphiti 客户端实例初始化完成")

    return client


async def close_graphiti_client():
    """关闭 Graphiti 客户端连接。"""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
        logger.info("Graphiti 客户端已关闭")
