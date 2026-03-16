<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="MiroFish Logo" width="75%"/>

**MiroFish-Zepless**

A Simple and Universal Swarm Intelligence Engine, Predicting Anything — Self-hosted without Zep Cloud
</br>
<em>简洁通用的群体智能引擎，预测万物 —— 无需 Zep Cloud 的本地部署版本</em>

[![GitHub stars](https://img.shields.io/github/stars/pobooo/MiroFish-zepless?style=social)](https://github.com/pobooo/MiroFish-zepless)
[![GitHub forks](https://img.shields.io/github/forks/pobooo/MiroFish-zepless?style=social)](https://github.com/pobooo/MiroFish-zepless/fork)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](./LICENSE)

[English](./README-EN.md) | [中文文档](./README.md)

</div>

## 🔀 About This Fork

This project is a modified fork of [**666ghj/MiroFish**](https://github.com/666ghj/MiroFish), with the following key change:

> **Removed Zep Cloud dependency → Replaced with self-hosted Neo4j + [Graphiti](https://github.com/getzep/graphiti)**

| Comparison | Original MiroFish | This Fork (Zepless) |
|-----------|-------------------|---------------------|
| Knowledge Graph | Zep Cloud (SaaS) | Neo4j + Graphiti (self-hosted) |
| Cost | Limited by Zep free tier | Completely free, unlimited |
| Dependencies | Requires Zep API Key | Requires local Neo4j |
| Data Privacy | Data goes through Zep cloud | Data stays local |

**The original project is licensed under AGPL-3.0. This fork follows the same license.**

## ⚡ Overview

**MiroFish** is a next-generation AI prediction engine powered by multi-agent technology. By extracting seed information from the real world (such as breaking news, policy drafts, or financial signals), it automatically constructs a high-fidelity parallel digital world. Within this space, thousands of intelligent agents with independent personalities, long-term memory, and behavioral logic freely interact and undergo social evolution. You can inject variables dynamically from a "God's-eye view" to precisely deduce future trajectories — **rehearse the future in a digital sandbox, and win decisions after countless simulations**.

> You only need to: Upload seed materials (data analysis reports or interesting novel stories) and describe your prediction requirements in natural language</br>
> MiroFish will return: A detailed prediction report and a deeply interactive high-fidelity digital world

## 🌐 Live Demo

Original demo environment: [mirofish-live-demo](https://666ghj.github.io/mirofish-demo/)

## 📸 Screenshots

<div align="center">
<table>
<tr>
<td><img src="./static/image/Screenshot/运行截图1.png" alt="Screenshot 1" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图2.png" alt="Screenshot 2" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图3.png" alt="Screenshot 3" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图4.png" alt="Screenshot 4" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图5.png" alt="Screenshot 5" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图6.png" alt="Screenshot 6" width="100%"/></td>
</tr>
</table>
</div>

## 🔄 Workflow

1. **Graph Building**: Seed extraction & Individual/collective memory injection & Neo4j + Graphiti graph construction
2. **Environment Setup**: Entity relationship extraction & Persona generation & Agent configuration injection
3. **Simulation**: Dual-platform parallel simulation & Auto-parse prediction requirements & Dynamic temporal memory updates
4. **Report Generation**: ReportAgent with rich toolset for deep interaction with post-simulation environment
5. **Deep Interaction**: Chat with any agent in the simulated world & Interact with ReportAgent

## 🚀 Quick Start

### Option 1: Source Code Deployment (Recommended)

#### Prerequisites

| Tool | Version | Description | Check Installation |
|------|---------|-------------|-------------------|
| **Node.js** | 18+ | Frontend runtime, includes npm | `node -v` |
| **Python** | ≥3.11, ≤3.12 | Backend runtime | `python --version` |
| **uv** | Latest | Python package manager | `uv --version` |
| **Neo4j** | 2024+ | Graph database | `neo4j version` |
| **Java** | 21+ | Neo4j runtime dependency | `java -version` |

#### 1. Install and Start Neo4j

> For detailed installation steps, see [graphiti/INSTALL.md](./graphiti/INSTALL.md)

**macOS (Homebrew):**

```bash
# Install Java 21 and Neo4j
brew install openjdk@21 neo4j

# Configure APOC plugin (required by Graphiti)
# See graphiti/INSTALL.md Section 3 for details

# Set Neo4j password
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
neo4j-admin dbms set-initial-password <your_password>

# Start Neo4j (recommended: use the provided script)
./graphiti/start_neo4j.sh
```

**Docker (easier):**

```bash
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_neo4j_password \
  -e NEO4J_PLUGINS='["apoc"]' \
  neo4j:2026-community
```

After startup, visit http://localhost:7474 to open the Neo4j Browser management interface.

#### 2. Configure Environment Variables

```bash
# Copy the example configuration file
cp .env.example .env

# Edit the .env file and fill in the required configuration
```

**Required Environment Variables:**

```env
# LLM API Configuration (supports any LLM API with OpenAI SDK format)
# Recommended: Alibaba Qwen-plus model via Bailian Platform: https://bailian.console.aliyun.com/
# High consumption, try simulations with fewer than 40 rounds first
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus

# Neo4j connection configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

#### 3. Install Dependencies

```bash
# One-click installation of all dependencies (root + frontend + backend)
npm run setup:all
```

Or install step by step:

```bash
# Install Node dependencies (root + frontend)
npm run setup

# Install Python dependencies (backend, auto-creates virtual environment)
npm run setup:backend
```

#### 4. Start Services

```bash
# Make sure Neo4j is running
./graphiti/start_neo4j.sh

# Start both frontend and backend (run from project root)
npm run dev
```

**Service URLs:**
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5001`
- Neo4j Browser: `http://localhost:7474`

**Start Individually:**

```bash
npm run backend   # Start backend only
npm run frontend  # Start frontend only
```

### Option 2: Docker Deployment

```bash
# 1. Configure environment variables
cp .env.example .env
# Edit .env, fill in LLM API Key and Neo4j password

# 2. Start (includes Neo4j + MiroFish)
docker compose up -d
```

The `docker-compose.yml` includes a Neo4j service that will be automatically started with APOC plugin configured.

Default port mapping: `3000 (frontend) / 5001 (backend) / 7474 (Neo4j Browser) / 7687 (Neo4j Bolt)`

## 📄 Acknowledgments

- **[666ghj/MiroFish](https://github.com/666ghj/MiroFish)** — The original project this fork is based on. MiroFish has received strategic support and incubation from Shanda Group.
- **[OASIS](https://github.com/camel-ai/oasis)** — MiroFish's simulation engine. Thanks to the CAMEL-AI team for their open-source contributions.
- **[Graphiti](https://github.com/getzep/graphiti)** — Zep's open-source knowledge graph framework, the core replacement in this fork.
- **[Neo4j](https://neo4j.com/)** — Graph database engine.

## 📝 License

This project is licensed under [AGPL-3.0](./LICENSE), consistent with the original project.

As required by AGPL-3.0 Section 5(a), the main modifications in this fork:
- Removed Zep Cloud dependency, replaced with Neo4j + Graphiti for local knowledge graph management
- Added Neo4j start/stop scripts and installation documentation
- Added local Embedding and CrossEncoder implementations
</div>
