FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    wget \
    build-essential \
    git \
    nmap \
    && rm -rf /var/lib/apt/lists/*

# 复制需要的文件到容器
COPY requirements.txt .
COPY main.py .
COPY __init__.py* ./
COPY data_acquisition ./data_acquisition
COPY data_processing ./data_processing
COPY network_topology ./network_topology
COPY holographic_mapping ./holographic_mapping
COPY realtime_search ./realtime_search
COPY user_interface ./user_interface
COPY static ./static
COPY templates ./templates

# 创建必要的目录
RUN mkdir -p config data/raw data/processed data/backups data/topology logs models

# 验证模块结构
RUN ls -la /app/holographic_mapping/

# 确保有正确的__init__.py文件
RUN touch /app/__init__.py
RUN touch /app/holographic_mapping/__init__.py
RUN touch /app/data_acquisition/__init__.py
RUN touch /app/data_processing/__init__.py
RUN touch /app/network_topology/__init__.py
RUN touch /app/realtime_search/__init__.py
RUN touch /app/user_interface/__init__.py

# 下载中文字体
RUN wget -O simhei.ttf "https://github.com/StellarCN/scp_zh/raw/refs/heads/master/fonts/SimHei.ttf"

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH="/app:${PYTHONPATH}"

# 运行应用
CMD ["python", "main.py"]