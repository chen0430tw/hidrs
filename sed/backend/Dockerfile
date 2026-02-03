FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建日志目录
RUN mkdir -p logs

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV ES_HOST=elasticsearch
ENV ES_PORT=9200
ENV ES_INDEX=socialdb
ENV DEBUG=True

# 暴露端口
EXPOSE 5000

# 运行应用
CMD ["python", "api_main.py"]