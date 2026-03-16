"""
Graphiti 集成模块（Zep Cloud 的开源替代）

提供:
    - LocalEmbedder: 本地 sentence-transformers 嵌入
    - LocalCrossEncoder: 轻量级重排序器
    - get_graphiti_client: Graphiti 客户端工厂（单例）
"""

from .local_embedder import LocalEmbedder
from .local_cross_encoder import LocalCrossEncoder
from .graphiti_client import get_graphiti_client, close_graphiti_client

__all__ = [
    "LocalEmbedder",
    "LocalCrossEncoder",
    "get_graphiti_client",
    "close_graphiti_client",
]
