#!/usr/bin/env sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
config_path="$project_root/agent/.env"
compose_path="$project_root/docker-compose.yml"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required." >&2
    exit 1
fi

if [ "${1:-}" = "down" ]; then
    docker compose --project-directory "$project_root" -f "$compose_path" down
    exit $?
fi

if [ "$#" -gt 0 ]; then
    echo "Usage: sh scripts/deploy-docker.sh [down]" >&2
    exit 1
fi

if [ ! -f "$config_path" ]; then
    echo "Missing agent/.env. Copy agent/Common/Configs/.env.example and configure it first." >&2
    exit 1
fi

set -a
. "$config_path"
set +a

for value in "${INTERVIEW_GUIDE_OPENAI_BASE_URL:-}" "${INTERVIEW_GUIDE_OPENAI_MODEL:-}" "${INTERVIEW_GUIDE_OPENAI_API_KEY:-}" "${INTERVIEW_GUIDE_EMBEDDING_BASE_URL:-}" "${INTERVIEW_GUIDE_EMBEDDING_MODEL:-}" "${INTERVIEW_GUIDE_EMBEDDING_API_KEY:-}" "${POSTGRES_PASSWORD:-}"; do
    if [ -z "$value" ] || [ "$value" = "replace-me" ]; then
        echo "agent/.env contains an unconfigured required value." >&2
        exit 1
    fi
done

: "${PIP_INDEX_URL:=https://pypi.tuna.tsinghua.edu.cn/simple}"
: "${MAVEN_MIRROR_URL:=https://maven.aliyun.com/repository/public}"
: "${NPM_REGISTRY:=https://registry.npmmirror.com}"
export PIP_INDEX_URL MAVEN_MIRROR_URL NPM_REGISTRY

docker compose --project-directory "$project_root" -f "$compose_path" up --build --detach --remove-orphans
docker compose --project-directory "$project_root" -f "$compose_path" ps
echo "Deployment completed: http://localhost ; RabbitMQ: http://localhost:15672"
