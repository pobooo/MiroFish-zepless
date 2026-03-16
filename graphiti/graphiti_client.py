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
        - EMBEDDING_MODEL (default: all-MiniLM-L6-v2)
    """
    global _client

    if _client is not None:
        return _client

    # Neo4j 配置
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")

    if not neo4j_password:
        raise ValueError("NEO4J_PASSWORD 环境变量未设置")

    # LLM 配置
    llm_api_key = os.getenv("LLM_API_KEY", "")
    llm_base_url = os.getenv("LLM_BASE_URL", "")
    llm_model = os.getenv("LLM_MODEL_NAME", "glm4.5-cdp")

    if not llm_api_key:
        raise ValueError("LLM_API_KEY 环境变量未设置")

    llm_config = LLMConfig(
        api_key=llm_api_key,
        base_url=llm_base_url,
        model=llm_model,
        small_model=llm_model,
    )
    llm_client = CompatOpenAIClient(config=llm_config)
    logger.info(f"LLM 客户端类型: {type(llm_client).__name__}, MRO: {[c.__name__ for c in type(llm_client).__mro__]}")

    # 本地 Embedder 和 CrossEncoder
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
    # Neo4j 配置
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")

    if not neo4j_password:
        raise ValueError("NEO4J_PASSWORD 环境变量未设置")

    # LLM 配置
    llm_api_key = os.getenv("LLM_API_KEY", "")
    llm_base_url = os.getenv("LLM_BASE_URL", "")
    llm_model = os.getenv("LLM_MODEL_NAME", "glm4.5-cdp")

    if not llm_api_key:
        raise ValueError("LLM_API_KEY 环境变量未设置")

    llm_config = LLMConfig(
        api_key=llm_api_key,
        base_url=llm_base_url,
        model=llm_model,
        small_model=llm_model,
    )
    llm_client = CompatOpenAIClient(config=llm_config)
    logger.info(f"[create] LLM 客户端类型: {type(llm_client).__name__}, has _create_structured_completion: {hasattr(llm_client, '_create_structured_completion')}")

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
    # Neo4j 配置
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")

    if not neo4j_password:
        raise ValueError("NEO4J_PASSWORD 环境变量未设置")

    # LLM 配置
    llm_api_key = os.getenv("LLM_API_KEY", "")
    llm_base_url = os.getenv("LLM_BASE_URL", "")
    llm_model = os.getenv("LLM_MODEL_NAME", "glm4.5-cdp")

    if not llm_api_key:
        raise ValueError("LLM_API_KEY 环境变量未设置")

    llm_config = LLMConfig(
        api_key=llm_api_key,
        base_url=llm_base_url,
        model=llm_model,
        small_model=llm_model,
    )
    llm_client = CompatOpenAIClient(config=llm_config)

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
