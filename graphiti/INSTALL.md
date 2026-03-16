# 安装步骤详解

本文档记录了从零安装 Neo4j + Graphiti 的完整过程，以便在新环境中复现。

---

## 1. 安装 Java（Neo4j 依赖）

Neo4j 2026.x 需要 Java 21+。

```bash
# macOS (Homebrew)
HOMEBREW_NO_AUTO_UPDATE=1 brew install openjdk@21

# 验证
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
java -version
# openjdk version "21.x.x"
```

> 如需系统全局可用，可添加符号链接：
> ```bash
> sudo ln -sfn /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk /Library/Java/JavaVirtualMachines/openjdk-21.jdk
> ```

---

## 2. 安装 Neo4j

```bash
# macOS (Homebrew)
HOMEBREW_NO_AUTO_UPDATE=1 brew install neo4j

# 验证
neo4j version
# 2026.02.2
```

### 安装位置

| 路径 | 内容 |
|------|------|
| `/opt/homebrew/opt/neo4j/libexec/` | Neo4j 主目录 |
| `/opt/homebrew/opt/neo4j/libexec/conf/neo4j.conf` | 配置文件 |
| `/opt/homebrew/opt/neo4j/libexec/plugins/` | 插件目录 |
| `/opt/homebrew/var/neo4j/data/` | 数据目录 |
| `/opt/homebrew/var/log/neo4j/` | 日志目录 |

---

## 3. 配置 APOC 插件

Graphiti 依赖 Neo4j 的 APOC 插件。Homebrew 安装的 Neo4j 自带 APOC jar，但在 `labs/` 目录下，需要复制到 `plugins/`：

```bash
# 复制 APOC jar
cp /opt/homebrew/Cellar/neo4j/2026.02.2/libexec/labs/apoc-2026.02.2-core.jar \
   /opt/homebrew/Cellar/neo4j/2026.02.2/libexec/plugins/
```

### 修改 neo4j.conf

在 `/opt/homebrew/opt/neo4j/libexec/conf/neo4j.conf` 中确保以下配置：

```properties
dbms.security.procedures.unrestricted=apoc.*
dbms.security.procedures.allowlist=apoc.*
```

---

## 4. 设置 Neo4j 密码

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
neo4j-admin dbms set-initial-password <your_password>
```

> 将 `<your_password>` 替换为你自己的密码，并确保与 `.env` 中的 `NEO4J_PASSWORD` 一致。

---

## 5. 启动 Neo4j

```bash
# 推荐方式（启动脚本已封装）
./graphiti/start_neo4j.sh

# 或手动启动
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
nohup neo4j console > /tmp/neo4j-output.log 2>&1 &
```

### 验证

```bash
# HTTP 接口
curl -s http://localhost:7474
# 应返回 JSON 信息

# Cypher Shell
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
cypher-shell -u neo4j -p <your_password> "RETURN 1 as test"

# APOC 验证
cypher-shell -u neo4j -p <your_password> \
  "SHOW PROCEDURES YIELD name WHERE name STARTS WITH 'apoc' RETURN count(name) as apoc_count"
# 应返回 174
```

---

## 6. 安装 graphiti-core

```bash
cd backend
uv pip install graphiti-core
# 安装版本：0.28.2
```

---

## 7. 配置环境变量

在项目根目录 `.env` 文件中添加：

```env
# ===== Neo4j + Graphiti 配置 =====
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

---

## 8. 验证全部连接

```bash
cd backend && .venv/bin/python3 ../graphiti/test_connection.py
```

预期输出：

```
初始化 Graphiti...
创建 indices 和 constraints...
✅ Schema 创建成功!
✅ Graphiti + Neo4j 全部验证通过!
```

---

## 常见问题

### Q: `brew services start neo4j` 启动失败？
A: brew services 的 plist 中没有设置 `JAVA_HOME`，导致找不到 Java。请使用 `./graphiti/start_neo4j.sh` 启动。

### Q: APOC 存储过程数量为 0？
A: 检查 APOC jar 是否在 `plugins/` 目录中，而不是 `labs/` 目录。复制后需重启 Neo4j。

### Q: Embedding 模型报错？
A: 如果你的 LLM API 不提供 embedding 模型，代码改造中需使用本地 `sentence-transformers` 实现自定义 Embedder。详见 `graphiti/local_embedder.py`。
