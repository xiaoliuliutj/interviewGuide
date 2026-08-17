ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

WORKDIR /app

# 先复制依赖清单以利用 Docker 构建缓存，业务代码变化时无需重复安装依赖。
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY requirements.txt ./
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt

COPY . ./agent

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --retries=12 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/internal/v1/health', timeout=2)" || exit 1

# 数据库迁移由 FastAPI startup 生命周期执行，服务启动前无需额外手工命令。
CMD ["uvicorn", "agent.Api.LLMApi:app", "--host", "0.0.0.0", "--port", "8000"]
