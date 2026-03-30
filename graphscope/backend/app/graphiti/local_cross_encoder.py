"""
本地 CrossEncoder（重排序器）实现

基于关键词重叠度进行轻量级重排序，不依赖 torch。
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
        """
        if not passages:
            return []

        query_tokens = set(_tokenize(query.lower()))

        if not query_tokens:
            return [(p, 0.0) for p in passages]

        scored = []
        for passage in passages:
            p_lower = passage.lower()
            matched = sum(1 for t in query_tokens if t in p_lower)
            score = matched / len(query_tokens)
            scored.append((passage, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored


def _tokenize(text: str) -> List[str]:
    """简单分词：英文按单词，中文按字符"""
    words = re.findall(r"[a-zA-Z]+", text)
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    return words + chars
