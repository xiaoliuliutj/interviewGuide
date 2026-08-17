#!/usr/bin/env sh

# 从项目根目录加载本地密钥配置，并通过 Docker Compose 一键构建、启动全部服务。
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
config_path="$project_root/agent/.env"
compose_path="$project_root/docker-compose.yml"

if ! command -v docker >/dev/null 2>&1; then
    echo "未检测到 Docker。请安装并启动 Docker 后重试。" >&2
    exit 1
fi

if [ ! -f "$config_path" ]; then
    echo "缺少 agent/.env。请先复制 agent/Common/Configs/.env.example 并填写模型密钥。" >&2
    exit 1
fi

# 配置文件仅允许由当前部署者维护，加载后使 Docker Compose 能读取数据库密码等变量。
set -a
. "$config_path"
set +a

for value in \
    "${INTERVIEW_GUIDE_OPENAI_BASE_URL:-}" \
    "${INTERVIEW_GUIDE_OPENAI_MODEL:-}" \
    "${INTERVIEW_GUIDE_OPENAI_API_KEY:-}" \
    "${INTERVIEW_GUIDE_EMBEDDING_BASE_URL:-}" \
    "${INTERVIEW_GUIDE_EMBEDDING_MODEL:-}" \
    "${INTERVIEW_GUIDE_EMBEDDING_API_KEY:-}" \
    "${POSTGRES_PASSWORD:-}"; do
    if [ -z "$value" ] || [ "$value" = "replace-me" ]; then
        echo "agent/.env 存在未配置的模型或数据库字段。" >&2
        exit 1
    fi
done

if [ "${1:-}" = "down" ]; then
    docker compose --project-directory "$project_root" -f "$compose_path" down
    exit $?
fi

if [ "$#" -gt 0 ]; then
    echo "用法：sh scripts/deploy-docker.sh [down]" >&2
    exit 1
fi

docker compose --project-directory "$project_root" -f "$compose_path" up --build --detach --remove-orphans
docker compose --project-directory "$project_root" -f "$compose_path" ps
echo "部署完成：前端入口 http://localhost ，RabbitMQ 管理入口 http://localhost:15672"
