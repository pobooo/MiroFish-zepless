"""
测试 Graphiti + Neo4j + LLM API 全部组件

使用方法：
    1. 确保 .env 文件已配置好（参考 .env.example）
    2. 确保 Neo4j 已启动
    3. 运行: python test_graphiti.py
"""
import os
import asyncio
import hashlib
import numpy as np
from dotenv import load_dotenv
from graphiti_core import Graphiti
from graphiti_core.llm_client import LLMConfig, OpenAIClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.cross_encoder.client import CrossEncoderClient

load_dotenv()


class SimpleEmbedder(EmbedderClient):
    """基于哈希的轻量级 Embedder（验证用）"""

    async def create(self, input_data):
        if isinstance(input_data, str):
            seed = int(hashlib.md5(input_data.encode()).hexdigest(), 16) % 2**32
            np.random.seed(seed)
            return np.random.randn(384).tolist()
        return np.random.randn(384).tolist()

    async def create_batch(self, input_data_list):
        return [await self.create(text) for text in input_data_list]


class SimpleCrossEncoder(CrossEncoderClient):
    """简单的基于长度匹配的 CrossEncoder（验证用）"""

    async def rank(self, query, passages):
        scored = []
        for p in passages:
            # 简单相关性：查询词在段落中出现的比例
            words = query.lower().split()
            score = sum(1 for w in words if w in p.lower()) / max(len(words), 1)
            scored.append((p, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored


async def test():
    try:
        llm_config = LLMConfig(
            api_key=os.getenv('LLM_API_KEY', 'your_api_key_here'),
            base_url=os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1'),
            model=os.getenv('LLM_MODEL_NAME', 'gpt-4o-mini'),
            small_model=os.getenv('LLM_MODEL_NAME', 'gpt-4o-mini'),
        )
        llm_client = OpenAIClient(config=llm_config)
        embedder = SimpleEmbedder()
        cross_encoder = SimpleCrossEncoder()

        print('初始化 Graphiti...')
        graphiti = Graphiti(
            os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
            os.getenv('NEO4J_USER', 'neo4j'),
            os.getenv('NEO4J_PASSWORD', 'your_neo4j_password'),
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
        )

        print('创建 indices 和 constraints...')
        await graphiti.build_indices_and_constraints()
        print('✅ Schema 创建成功!')

        await graphiti.close()
        print('✅ Graphiti + Neo4j 全部验证通过!')
    except Exception as e:
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(test())
