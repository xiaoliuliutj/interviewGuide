FROM python:3.12-slim

WORKDIR /app

# 先复制依赖清单以利用 Docker 构建缓存，业务代码变化时无需重复安装依赖。
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./agent

EXPOSE 8000

# 数据库迁移由 FastAPI startup 生命周期执行，服务启动前无需额外手工命令。
CMD ["uvicorn", "agent.api.application:app", "--host", "0.0.0.0", "--port", "8000"]
