#!/bin/bash
# Neo4j 停止脚本
# 用法: ./graphiti/stop_neo4j.sh

set -e

export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home

echo "🛑 停止 Neo4j..."

# 方式1: 使用 neo4j stop 命令
neo4j stop 2>/dev/null && echo "✅ Neo4j 已停止" && exit 0

# 方式2: 查找并杀掉进程
NEO4J_PID=$(pgrep -f "org.neo4j" 2>/dev/null || true)
if [ -n "$NEO4J_PID" ]; then
    kill "$NEO4J_PID" 2>/dev/null
    echo "✅ Neo4j 进程 (PID: $NEO4J_PID) 已终止"
else
    echo "ℹ️  Neo4j 未在运行"
fi
