"""
Graphiti + Neo4j 连接 & Embedding 综合验证脚本

用法:
    cd MiroFish
    backend/.venv/bin/python3 -m graphiti.test_connection
"""

import sys
import os
import asyncio
import time

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 强制 flush 打印
_print = print
def print(*a, **k):
    _print(*a, **k, flush=True)


async def test_embedding():
    """测试本地 Embedding"""
    print("\n[1/3] 测试本地 Embedding 模型")
    from graphiti.local_embedder import LocalEmbedder

    t0 = time.time()
    embedder = LocalEmbedder()
    vec = await embedder.create("测试文本")
    print(f"  单条 Embedding: 维度={len(vec)}, 耗时={time.time()-t0:.1f}s")

    t1 = time.time()
    vecs = await embedder.create_batch(["文本A", "文本B", "文本C"])
    print(f"  批量 Embedding: {len(vecs)}条, 耗时={time.time()-t1:.1f}s")
    print("  ✅ Embedding 正常")


async def test_cross_encoder():
    """测试 CrossEncoder"""
    print("\n[2/3] 测试 CrossEncoder（重排序器）")
    from graphiti.local_cross_encoder import LocalCrossEncoder

    ce = LocalCrossEncoder()
    results = await ce.rank("媒体报道", [
        "央视新闻发布专题报道",
        "今天天气晴朗",
        "各大媒体纷纷跟进报道",
    ])
    print("  排序结果:")
    for text, score in results:
        print(f"    {score:.2f} - {text}")
    print("  ✅ CrossEncoder 正常")


async def test_neo4j():
    """测试 Neo4j + Graphiti 连接"""
    print("\n[3/3] 测试 Neo4j + Graphiti 连接")
    from graphiti_core import Graphiti
    from graphiti_core.llm_client import LLMConfig, OpenAIClient
    from graphiti.local_embedder import LocalEmbedder
    from graphiti.local_cross_encoder import LocalCrossEncoder

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")
    llm_api_key = os.getenv("LLM_API_KEY", "")
    llm_base_url = os.getenv("LLM_BASE_URL", "")
    llm_model = os.getenv("LLM_MODEL_NAME", "gpt-4o-mini")

    llm_config = LLMConfig(
        api_key=llm_api_key,
        base_url=llm_base_url,
        model=llm_model,
        small_model=llm_model,
    )

    graphiti = Graphiti(
        neo4j_uri, neo4j_user, neo4j_password,
        llm_client=OpenAIClient(config=llm_config),
        embedder=LocalEmbedder(),
        cross_encoder=LocalCrossEncoder(),
    )

    t0 = time.time()
    await graphiti.build_indices_and_constraints()
    print(f"  Schema 验证: {time.time()-t0:.1f}s")

    await graphiti.close()
    print("  ✅ Neo4j + Graphiti 连接正常")


async def main():
    print("=" * 50)
    print("Graphiti 综合验证")
    print("=" * 50)

    try:
        await test_embedding()
        await test_cross_encoder()
        await test_neo4j()
        print("\n" + "=" * 50)
        print("✅ 全部验证通过!")
        print("=" * 50)
    except Exception as e:
        import traceback
        print(f"\n❌ 验证失败: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
