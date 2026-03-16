# Graphiti + Neo4j（Zep Cloud 的开源替代方案）

## 概述

本项目原使用 [Zep Cloud](https://app.getzep.com/) 作为知识图谱服务，但受限于免费额度（每月有限）。  
现改用 Zep 官方开源的 **[Graphiti](https://github.com/getzep/graphiti)** 框架 + **Neo4j** 图数据库进行本地自部署，实现无限制使用。

| 组件 | 版本 | 说明 |
|------|------|------|
| Neo4j | 2026.02.2 | 图数据库，通过 Homebrew 安装 |
| APOC 插件 | 2026.02.2-core | Neo4j 扩展插件，174 个存储过程 |
| graphiti-core | 0.28.2 | Zep 开源的 Python 图谱框架 |
| OpenJDK | 21 | Neo4j 运行时依赖 |

## 目录结构

```
graphiti/
├── README.md                 # 本文件 - 总体说明
├── INSTALL.md                # 安装步骤详解
├── MIGRATION.md              # Zep → Graphiti 代码改造指南
├── start_neo4j.sh            # Neo4j 启动脚本
├── stop_neo4j.sh             # Neo4j 停止脚本
└── test_connection.py        # 连接验证脚本
```

## 快速开始

### 1. 启动 Neo4j

```bash
./graphiti/start_neo4j.sh
```

### 2. 验证连接

```bash
cd backend && .venv/bin/python3 ../graphiti/test_connection.py
```

### 3. 停止 Neo4j

```bash
./graphiti/stop_neo4j.sh
```

## 环境变量（配置在项目根目录 `.env` 中）

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

## 端口说明

| 端口 | 协议 | 用途 |
|------|------|------|
| 7687 | Bolt | Neo4j 数据库连接（Graphiti 使用） |
| 7474 | HTTP | Neo4j 浏览器管理界面 |

访问 http://localhost:7474 可打开 Neo4j Browser 进行可视化查询。

## Embedding 方案

如果你的 LLM API 不提供 embedding 模型，可通过本地 `sentence-transformers` 解决：

- **当前模型**: `all-MiniLM-L6-v2`（384维，22M 参数，首次加载 ~7s，后续 ~0.5s/批）
- **切换中文模型**: 设置环境变量 `EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2`（需先下载）
- **代码位置**: `graphiti/local_embedder.py`

### 在代码中使用

```python
from graphiti.graphiti_client import get_graphiti_client

# 获取全局 Graphiti 客户端（自动包含本地 Embedding）
graphiti = await get_graphiti_client()
```

## 注意事项

- Neo4j 启动需要 `JAVA_HOME` 环境变量，启动脚本已自动处理
- `brew services start neo4j` 可能因缺少 JAVA_HOME 而失败，建议使用本目录的启动脚本
