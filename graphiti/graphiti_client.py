"""
Graphiti 客户端工厂（单例模式）

统一管理 Graphiti 的初始化和配置，提供全局单例。
所有需要 Graphiti 的模块都应该通过本模块获取实例。

使用方式:
    from graphiti.graphiti_client import get_graphiti_client

    # 获取已初始化的 Graphiti 客户端
    graphiti = await get_graphiti_client()

    # 使用完毕后关闭
    await close_graphiti_client()
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

# 支持 Responses API 的 API 端点关键字
# 如果 LLM_BASE_URL 包含以下关键字，使用原生 OpenAIClient (responses.parse)
# 其他端点统一使用 CompatOpenAIClient (chat.completions + json_schema 硬约束)
_RESPONSES_API_HOSTS = [
    "api.openai.com",
    "azure.openai.com",      # Azure OpenAI 也支持
]


def _use_responses_api(base_url: str) -> bool:
    """
    判断给定的 API 端点是否支持 OpenAI Responses API (/v1/responses)。
    
    - 支持 Responses API → 使用 OpenAIClient (responses.parse)
    - 不支持 → 使用 CompatOpenAIClient (chat.completions + json_schema 硬约束)
    
    两者都是 constrained decoding，100% 格式正确，区别只在 API 端点。
    
    也可以通过环境变量 LLM_USE_STRUCTURED_OUTPUT=true 强制使用 Responses API。
    """
    # 环境变量强制覆盖
    force_structured = os.getenv("LLM_USE_STRUCTURED_OUTPUT", "").lower()
    if force_structured == "true":
        return True
    if force_structured == "false":
        return False
    
    # 根据 URL 自动判断
    base_url_lower = base_url.lower()
    return any(host in base_url_lower for host in _RESPONSES_API_HOSTS)


def _create_llm_client(llm_config: LLMConfig):
    """
    根据 API 端点自动选择合适的 LLM 客户端。
    
    两种方案都使用 constrained decoding（硬约束），格式 100% 正确：
    - OpenAI 原生 API → OpenAIClient（Responses API: responses.parse）
    - 第三方代理（one-api 等） → CompatOpenAIClient（Chat Completions API + json_schema）
    """
    base_url = llm_config.base_url or ""
    
    if _use_responses_api(base_url):
        from graphiti_core.llm_client import OpenAIClient
        client = OpenAIClient(config=llm_config)
        logger.info(
            f"LLM 客户端: OpenAIClient (Responses API 硬约束), "
            f"base_url={base_url}, model={llm_config.model}"
        )
    else:
        client = CompatOpenAIClient(config=llm_config)
        logger.info(
            f"LLM 客户端: CompatOpenAIClient (json_schema 硬约束), "
            f"base_url={base_url}, model={llm_config.model}"
        )
    
    return client


def _get_neo4j_config() -> tuple[str, str, str]:
    """读取 Neo4j 配置，返回 (uri, user, password)。"""
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")

    if not neo4j_password:
        raise ValueError("NEO4J_PASSWORD 环境变量未设置")
    
    return neo4j_uri, neo4j_user, neo4j_password


def _get_llm_config() -> LLMConfig:
    """读取 LLM 配置并返回 LLMConfig。"""
    llm_api_key = os.getenv("LLM_API_KEY", "")
    llm_base_url = os.getenv("LLM_BASE_URL", "")
    llm_model = os.getenv("LLM_MODEL_NAME", "glm4.5-cdp")

    if not llm_api_key:
        raise ValueError("LLM_API_KEY 环境变量未设置")

    return LLMConfig(
        api_key=llm_api_key,
        base_url=llm_base_url,
        model=llm_model,
        small_model=llm_model,
    )


async def get_graphiti_client() -> Graphiti:
    """
    获取 Graphiti 客户端单例。
    
    首次调用时初始化，后续调用返回同一实例。
    从环境变量读取配置:
        - NEO4J_URI (default: bolt://localhost:7687)
        - NEO4J_USER (default: neo4j)
        - NEO4J_PASSWORD (required)
        - LLM_API_KEY (required)
        - LLM_BASE_URL (required)
        - LLM_MODEL_NAME (default: glm4.5-cdp)
        - LLM_USE_STRUCTURED_OUTPUT (optional: true/false, 强制指定是否使用 Structured Output)
        - EMBEDDING_MODEL (default: all-MiniLM-L6-v2)
    """
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

    # 确保 schema 已创建
    await _client.build_indices_and_constraints()
    logger.info("Graphiti 客户端初始化完成")

    return _client


async def create_graphiti_client() -> Graphiti:
    """
    创建一个新的 Graphiti 客户端实例（非单例）。
    
    用于在独立事件循环中运行的场景（如后台线程），
    避免与主事件循环的单例冲突。
    调用方负责在使用完毕后调用 client.close()。
    """
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


async def create_graphiti_client_lite() -> Graphiti:
    """
    创建一个轻量的 Graphiti 客户端实例（跳过索引创建）。
    
    用于只读操作（如读取节点、边），避免每次创建时重建索引的开销。
    索引在服务启动时已由 get_graphiti_client() 或 create_graphiti_client() 创建。
    """
    neo4j_uri, neo4j_user, neo4j_password = _get_neo4j_config()
    llm_config = _get_llm_config()
    llm_client = _create_llm_client(llm_config)

    embedder = LocalEmbedder()
    cross_encoder = LocalCrossEncoder()

    client = Graphiti(
        neo4j_uri,
        neo4j_user,
        neo4j_password,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
    )

    # 跳过 build_indices_and_constraints()，索引已在启动时创建
    logger.debug("创建轻量 Graphiti 客户端实例（跳过索引）")

    return client


async def close_graphiti_client():
    """关闭 Graphiti 客户端连接"""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
        logger.info("Graphiti 客户端已关闭")
