#!/usr/bin/env sh
set -eu

echo "=================================="
echo "从GitHub同步代码并部署到Docker"
echo "=================================="

# 1. 拉取最新代码
echo "步骤 1/3: 拉取GitHub最新代码..."
git pull origin main

# 2. 停止旧服务
echo "步骤 2/3: 停止旧服务..."
sh "$(dirname "$0")/deploy-docker.sh" down 2>/dev/null || true

# 3. 重新部署
echo "步骤 3/3: 重新构建并部署..."
sh "$(dirname "$0")/deploy-docker.sh"

echo "=================================="
echo "✓ 同步并部署完成！"
echo "=================================="
