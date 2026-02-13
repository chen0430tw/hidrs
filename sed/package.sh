#!/bin/bash
# 银狼数据安全平台 - 打包脚本

VERSION=${1:-$(date +%Y%m%d)}
PACKAGE_NAME="silver-wolf-platform-${VERSION}"

echo "打包银狼数据安全平台 v${VERSION}..."

# 创建临时目录
mkdir -p /tmp/${PACKAGE_NAME}

# 复制文件（排除不需要的）
rsync -av --progress . /tmp/${PACKAGE_NAME}/ \
    --exclude=node_modules \
    --exclude=.git \
    --exclude=__pycache__ \
    --exclude='*.pyc' \
    --exclude=dist \
    --exclude=.env \
    --exclude=logs \
    --exclude='es-data' \
    --exclude='redis-data'

# 压缩
cd /tmp
tar czf ${PACKAGE_NAME}.tar.gz ${PACKAGE_NAME}/
rm -rf ${PACKAGE_NAME}

echo ""
echo "打包完成: /tmp/${PACKAGE_NAME}.tar.gz"
echo "大小: $(du -h /tmp/${PACKAGE_NAME}.tar.gz | cut -f1)"
