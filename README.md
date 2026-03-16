<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="MiroFish Logo" width="75%"/>

**MiroFish-Zepless**

简洁通用的群体智能引擎，预测万物 —— 无需 Zep Cloud 的本地部署版本
</br>
<em>A Simple and Universal Swarm Intelligence Engine — Zep-free, Self-hosted with Neo4j + Graphiti</em>

[![GitHub stars](https://img.shields.io/github/stars/pobooo/MiroFish-zepless?style=social)](https://github.com/pobooo/MiroFish-zepless)
[![GitHub forks](https://img.shields.io/github/forks/pobooo/MiroFish-zepless?style=social)](https://github.com/pobooo/MiroFish-zepless/fork)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](./LICENSE)

[English](./README-EN.md) | [中文文档](./README.md)

</div>

## 🔀 关于本 Fork

本项目是 [**666ghj/MiroFish**](https://github.com/666ghj/MiroFish) 的 Fork 修改版，主要改动为：

> **移除 Zep Cloud 依赖 → 改用 Neo4j + [Graphiti](https://github.com/getzep/graphiti) 本地部署**

| 对比项 | 原版 MiroFish | 本 Fork (Zepless) |
|--------|--------------|-------------------|
| 知识图谱 | Zep Cloud (云服务) | Neo4j + Graphiti (本地自部署) |
| 费用 | 受限于 Zep 免费额度 | 完全免费，无限制 |
| 依赖 | 需要 Zep API Key | 需要本地安装 Neo4j |
| 数据隐私 | 数据经 Zep 云端 | 数据完全在本地 |

**原项目采用 AGPL-3.0 协议，本 Fork 遵循相同协议。**

## ⚡ 项目概述

**MiroFish** 是一款基于多智能体技术的新一代 AI 预测引擎。通过提取现实世界的种子信息（如突发新闻、政策草案、金融信号），自动构建出高保真的平行数字世界。在此空间内，成千上万个具备独立人格、长期记忆与行为逻辑的智能体进行自由交互与社会演化。你可透过「上帝视角」动态注入变量，精准推演未来走向——**让未来在数字沙盘中预演，助决策在百战模拟后胜出**。

> 你只需：上传种子材料（数据分析报告或者有趣的小说故事），并用自然语言描述预测需求</br>
> MiroFish 将返回：一份详尽的预测报告，以及一个可深度交互的高保真数字世界

## 🌐 在线体验

原版 Demo 演示环境：[mirofish-live-demo](https://666ghj.github.io/mirofish-demo/)

## 📸 系统截图

<div align="center">
<table>
<tr>
<td><img src="./static/image/Screenshot/运行截图1.png" alt="截图1" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图2.png" alt="截图2" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图3.png" alt="截图3" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图4.png" alt="截图4" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图5.png" alt="截图5" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图6.png" alt="截图6" width="100%"/></td>
</tr>
</table>
</div>

## 🔄 工作流程

1. **图谱构建**：现实种子提取 & 个体与群体记忆注入 & Neo4j + Graphiti 图谱构建
2. **环境搭建**：实体关系抽取 & 人设生成 & 环境配置Agent注入仿真参数
3. **开始模拟**：双平台并行模拟 & 自动解析预测需求 & 动态更新时序记忆
4. **报告生成**：ReportAgent拥有丰富的工具集与模拟后环境进行深度交互
5. **深度互动**：与模拟世界中的任意一位进行对话 & 与ReportAgent进行对话

## 🚀 快速开始

### 一、源码部署（推荐）

#### 前置要求

| 工具 | 版本要求 | 说明 | 安装检查 |
|------|---------|------|---------|
| **Node.js** | 18+ | 前端运行环境，包含 npm | `node -v` |
| **Python** | ≥3.11, ≤3.12 | 后端运行环境 | `python --version` |
| **uv** | 最新版 | Python 包管理器 | `uv --version` |
| **Neo4j** | 2024+ | 图数据库 | `neo4j version` |
| **Java** | 21+ | Neo4j 运行时依赖 | `java -version` |

#### 1. 安装并启动 Neo4j

> 详细安装步骤见 [graphiti/INSTALL.md](./graphiti/INSTALL.md)

**macOS (Homebrew):**

```bash
# 安装 Java 21 和 Neo4j
brew install openjdk@21 neo4j

# 配置 APOC 插件（Graphiti 依赖）
# 详见 graphiti/INSTALL.md 第 3 节

# 设置 Neo4j 密码
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
neo4j-admin dbms set-initial-password <your_password>

# 启动 Neo4j（推荐使用项目提供的脚本）
./graphiti/start_neo4j.sh
```

**Docker（更简单）:**

```bash
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_neo4j_password \
  -e NEO4J_PLUGINS='["apoc"]' \
  neo4j:2026-community
```

启动后访问 http://localhost:7474 可打开 Neo4j 浏览器管理界面。

#### 2. 配置环境变量

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑 .env 文件，填入必要的配置
```

**必需的环境变量：**

```env
# LLM API配置（支持 OpenAI SDK 格式的任意 LLM API）
# 推荐使用阿里百炼平台 qwen-plus 模型：https://bailian.console.aliyun.com/
# 注意消耗较大，可先进行小于 40 轮的模拟尝试
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus

# Neo4j 连接配置
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

#### 3. 安装依赖

```bash
# 一键安装所有依赖（根目录 + 前端 + 后端）
npm run setup:all
```

或者分步安装：

```bash
# 安装 Node 依赖（根目录 + 前端）
npm run setup

# 安装 Python 依赖（后端，自动创建虚拟环境）
npm run setup:backend
```

#### 4. 启动服务

```bash
# 确保 Neo4j 已启动
./graphiti/start_neo4j.sh

# 同时启动前后端（在项目根目录执行）
npm run dev
```

**服务地址：**
- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:5001`
- Neo4j 浏览器：`http://localhost:7474`

**单独启动：**

```bash
npm run backend   # 仅启动后端
npm run frontend  # 仅启动前端
```

### 二、Docker 部署

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM API Key 和 Neo4j 密码

# 2. 启动（包含 Neo4j + MiroFish）
docker compose up -d
```

`docker-compose.yml` 已包含 Neo4j 服务，会自动启动并配置好 APOC 插件。

默认端口映射：`3000（前端）/ 5001（后端）/ 7474（Neo4j 浏览器）/ 7687（Neo4j Bolt）`

## 📄 致谢

- **[666ghj/MiroFish](https://github.com/666ghj/MiroFish)** — 原始项目，本 Fork 基于此修改。MiroFish 得到了盛大集团的战略支持和孵化。
- **[OASIS](https://github.com/camel-ai/oasis)** — MiroFish 的仿真引擎，感谢 CAMEL-AI 团队的开源贡献。
- **[Graphiti](https://github.com/getzep/graphiti)** — Zep 开源的知识图谱框架，本 Fork 的核心替代方案。
- **[Neo4j](https://neo4j.com/)** — 图数据库引擎。

## 📝 协议

本项目遵循 [AGPL-3.0](./LICENSE) 协议，与原项目保持一致。

根据 AGPL-3.0 第 5(a) 条要求，本修改版本的主要改动：
- 移除 Zep Cloud 依赖，改用 Neo4j + Graphiti 进行本地知识图谱管理
- 新增 Neo4j 启动/停止脚本及安装文档
- 新增本地 Embedding 和 CrossEncoder 实现
</div>
