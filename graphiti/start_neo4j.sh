#!/bin/bash
# Neo4j 启动脚本
# 用法: ./graphiti/start_neo4j.sh

set -e

# 设置 JAVA_HOME
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home

# 检查 Java
if [ ! -d "$JAVA_HOME" ]; then
    echo "❌ Java 21 未安装，请运行: brew install openjdk@21"
    exit 1
fi

# 检查 Neo4j 是否已在运行
if curl -s -o /dev/null -w "%{http_code}" http://localhost:7474 2>/dev/null | grep -q "200"; then
    echo "✅ Neo4j 已在运行 (http://localhost:7474)"
    exit 0
fi

# 停止可能残留的 brew service
brew services stop neo4j 2>/dev/null || true

# 以后台方式启动 Neo4j
echo "🚀 启动 Neo4j..."
nohup neo4j console > /tmp/neo4j-output.log 2>&1 &
NEO4J_PID=$!
echo "   PID: $NEO4J_PID"

# 等待启动
echo "   等待 Neo4j 就绪..."
for i in $(seq 1 30); do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:7474 2>/dev/null | grep -q "200"; then
        echo "✅ Neo4j 启动成功!"
        echo "   HTTP:  http://localhost:7474"
        echo "   Bolt:  bolt://localhost:7687"
        echo "   用户:  neo4j"
        echo "   密码:  (见 .env 中的 NEO4J_PASSWORD)"
        exit 0
    fi
    sleep 1
done

echo "⚠️  Neo4j 启动超时，请检查日志: /tmp/neo4j-output.log"
exit 1
