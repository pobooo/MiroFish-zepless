"""
本地 Embedding 实现（基于 sentence-transformers）

替代 Zep Cloud / OpenAI 的 embedding 接口，供 Graphiti 使用。
支持语义搜索、实体消歧、关系去重等核心功能。

使用方式:
    from graphiti.local_embedder import LocalEmbedder
    embedder = LocalEmbedder()

可选模型（按需切换）:
    - all-MiniLM-L6-v2         英文模型，22M 参数，384维，最快（默认）
    - paraphrase-multilingual-MiniLM-L12-v2  多语言，118M 参数，384维，中文更好
    - moka-ai/m3e-base         中文专用，基于 BERT，768维

通过环境变量切换:
    EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
"""

import os
import logging
import threading
from typing import List, Union

from graphiti_core.embedder.client import EmbedderClient

logger = logging.getLogger(__name__)

# 默认模型（英文，体积小，速度快）
DEFAULT_MODEL = "all-MiniLM-L6-v2"

# 类级别模型缓存和锁，避免多个 LocalEmbedder 实例重复加载同一模型
_model_cache: dict = {}
_model_lock = threading.Lock()


class LocalEmbedder(EmbedderClient):
    """基于 sentence-transformers 的本地 Embedding 客户端"""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)

    @property
    def model(self):
        """延迟加载模型，使用线程锁保证并发安全，类级别缓存避免重复加载"""
        if self.model_name not in _model_cache:
            with _model_lock:
                # 双重检查：获取锁后再次确认
                if self.model_name not in _model_cache:
                    logger.info(f"加载 Embedding 模型: {self.model_name}")
                    from sentence_transformers import SentenceTransformer
                    _model_cache[self.model_name] = SentenceTransformer(self.model_name)
                    dim = _model_cache[self.model_name].get_sentence_embedding_dimension()
                    logger.info(f"Embedding 模型就绪: {self.model_name} (维度: {dim})")
        return _model_cache[self.model_name]

    async def create(self, input_data: Union[str, List[str]]) -> List[float]:
        """生成单条文本的 embedding 向量"""
        if isinstance(input_data, list):
            input_data = input_data[0] if input_data else ""
        embedding = self.model.encode(input_data)
        return embedding.tolist()

    async def create_batch(self, input_data_list: List[str]) -> List[List[float]]:
        """批量生成 embedding 向量"""
        embeddings = self.model.encode(input_data_list)
        return embeddings.tolist()
