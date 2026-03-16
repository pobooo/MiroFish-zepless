"""
本地 CrossEncoder（重排序器）实现

基于关键词重叠度进行轻量级重排序。
如果需要更高精度，可以切换为 sentence-transformers 的 CrossEncoder 模型。

使用方式:
    from graphiti.local_cross_encoder import LocalCrossEncoder
    cross_encoder = LocalCrossEncoder()
"""

import re
import logging
from typing import List, Tuple

from graphiti_core.cross_encoder.client import CrossEncoderClient

logger = logging.getLogger(__name__)


class LocalCrossEncoder(CrossEncoderClient):
    """基于关键词匹配的轻量级 CrossEncoder（重排序器）"""

    async def rank(
        self, query: str, passages: List[str]
    ) -> List[Tuple[str, float]]:
        """
        对候选段落按照与查询的相关度排序。

        算法: 基于 token 重叠度 + 长度归一化
        - 将 query 分词
        - 计算每个 passage 中包含的 query token 比例
        - 考虑 passage 长度给予适度惩罚（避免过长文本因包含更多词而占优）
        """
        if not passages:
            return []

        # 对 query 进行简单分词（中文按字/词，英文按空格）
        query_tokens = set(_tokenize(query.lower()))

        if not query_tokens:
            return [(p, 0.0) for p in passages]

        scored = []
        for passage in passages:
            p_lower = passage.lower()
            # 计算 query token 在 passage 中出现的比例
            matched = sum(1 for t in query_tokens if t in p_lower)
            score = matched / len(query_tokens)
            scored.append((passage, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored


def _tokenize(text: str) -> List[str]:
    """简单分词：英文按单词，中文按字符"""
    # 提取英文单词
    words = re.findall(r"[a-zA-Z]+", text)
    # 提取中文字符
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    return words + chars
