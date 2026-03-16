# Zep Cloud → Graphiti 代码改造指南

## 概述

MiroFish 项目中有 **7 个文件** 深度使用了 `zep_cloud` SDK，需要逐步改造为 `graphiti-core` API。

---

## 涉及文件清单

| 文件 | 功能 | 改造难度 | 优先级 |
|------|------|---------|--------|
| `app/services/graph_builder.py` | 图谱创建、数据写入、本体定义 | ⭐⭐⭐ 高 | P0 |
| `app/utils/zep_paging.py` | 分页查询封装 | ⭐⭐ 中 | P0 |
| `app/services/zep_entity_reader.py` | 实体/关系读取与过滤 | ⭐⭐⭐ 高 | P1 |
| `app/services/zep_tools.py` | 图谱搜索工具（供 Report Agent 用） | ⭐⭐⭐ 高 | P1 |
| `app/services/zep_graph_memory_updater.py` | 模拟运行中动态更新图谱 | ⭐⭐ 中 | P2 |
| `app/services/oasis_profile_generator.py` | 读取图谱实体生成 Agent Profile | ⭐⭐ 中 | P2 |
| `app/services/ontology_generator.py` | 本体类型生成（无直接 Zep 调用） | ⭐ 低 | P3 |

---

## API 映射表

### 图谱管理

| Zep Cloud API | Graphiti API | 说明 |
|---------------|-------------|------|
| `zep.graph.create(name, ...)` | `Graphiti(uri, user, pwd)` | Graphiti 实例即代表一个图谱 |
| `zep.graph.delete(graph_id)` | 需手动清除 Neo4j 数据 | 无直接等价 API |
| `zep.graph.get(graph_id)` | 直接查询 Neo4j | 无直接等价 API |

### 数据写入

| Zep Cloud API | Graphiti API | 说明 |
|---------------|-------------|------|
| `zep.graph.episode.add(data=[EpisodeData(...)])` | `graphiti.add_episode(...)` | 写入文本并自动抽取实体/关系 |
| `EntityEdgeSourceTarget` | 无需（自动抽取） | Graphiti 自动处理 |

### 本体定义

| Zep Cloud API | Graphiti API | 说明 |
|---------------|-------------|------|
| `zep.graph.set_entity_types(graph_id, types)` | `graphiti.add_entity_type(...)` | 定义实体类型 |
| `zep.graph.set_relation_types(graph_id, types)` | `graphiti.add_relation_type(...)` | 定义关系类型 |

### 搜索

| Zep Cloud API | Graphiti API | 说明 |
|---------------|-------------|------|
| `zep.graph.search(graph_id, query, ...)` | `graphiti.search(query, ...)` | 混合语义+BM25 搜索 |
| `zep.graph.edge.search(...)` | `graphiti.search(...)` | 搜索结果包含边信息 |

### 分页查询

| Zep Cloud API | Graphiti API | 说明 |
|---------------|-------------|------|
| `zep.graph.node.list_by_graph_id(graph_id, ...)` | 直接 Neo4j Cypher 查询 | `MATCH (n) RETURN n` |
| `zep.graph.edge.list_by_graph_id(graph_id, ...)` | 直接 Neo4j Cypher 查询 | `MATCH ()-[r]->() RETURN r` |

---

## 自定义组件

由于 LLM API 不提供 embedding 模型，需要自定义以下组件：

### 1. Embedder（向量嵌入）

```python
from graphiti_core.embedder.client import EmbedderClient
from sentence_transformers import SentenceTransformer

class LocalEmbedder(EmbedderClient):
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)
    
    async def create(self, input_data):
        return self.model.encode(input_data).tolist()
    
    async def create_batch(self, input_data_list):
        return self.model.encode(input_data_list).tolist()
```

### 2. CrossEncoder（重排序器）

```python
from graphiti_core.cross_encoder.client import CrossEncoderClient

class SimpleCrossEncoder(CrossEncoderClient):
    async def rank(self, query, passages):
        scored = []
        for p in passages:
            words = query.lower().split()
            score = sum(1 for w in words if w in p.lower()) / max(len(words), 1)
            scored.append((p, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
```

### 3. LLM Client（使用 GLM API）

```python
from graphiti_core.llm_client import LLMConfig, OpenAIClient

llm_config = LLMConfig(
    api_key=os.getenv('LLM_API_KEY'),
    base_url=os.getenv('LLM_BASE_URL'),
    model=os.getenv('LLM_MODEL_NAME'),
    small_model=os.getenv('LLM_MODEL_NAME'),
)
llm_client = OpenAIClient(config=llm_config)
```

---

## 改造步骤建议

### Phase 1：基础设施层（P0）
1. 创建 `app/services/graphiti_client.py` — Graphiti 客户端工厂（单例），统一初始化和配置
2. 改造 `app/utils/zep_paging.py` → `app/utils/graph_paging.py` — 改用 Neo4j Cypher 分页

### Phase 2：核心功能（P1）
3. 改造 `graph_builder.py` — 图谱创建和数据写入
4. 改造 `zep_entity_reader.py` — 实体读取和过滤
5. 改造 `zep_tools.py` — 搜索工具

### Phase 3：模拟功能（P2）
6. 改造 `zep_graph_memory_updater.py` — 动态记忆更新
7. 改造 `oasis_profile_generator.py` — Agent Profile 生成

### Phase 4：清理
8. 从 `requirements.txt` 移除 `zep-cloud`
9. 删除旧的 `zep_cloud` 相关代码
10. 更新 `.env` 移除 `ZEP_API_KEY`
