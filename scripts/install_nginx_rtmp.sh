#!/bin/bash
# install_nginx_rtmp.sh
# 安装 nginx + nginx-rtmp-module 流媒体服务器

set -e

echo "===== HIDRS 流媒体服务器安装脚本 ====="
echo ""

# 检查是否为root用户
if [[ $EUID -ne 0 ]]; then
   echo "⚠️  此脚本需要root权限，请使用sudo运行"
   exit 1
fi

# 系统检测
if [ -f /etc/debian_version ]; then
    PKG_MANAGER="apt"
    PKG_UPDATE="apt update"
    PKG_INSTALL="apt install -y"
elif [ -f /etc/redhat-release ]; then
    PKG_MANAGER="yum"
    PKG_UPDATE="yum makecache"
    PKG_INSTALL="yum install -y"
else
    echo "❌ 不支持的操作系统"
    exit 1
fi

echo "📦 安装依赖包..."
$PKG_UPDATE
$PKG_INSTALL build-essential libpcre3 libpcre3-dev libssl-dev zlib1g-dev wget git

# 版本配置
NGINX_VERSION="1.24.0"
RTMP_MODULE_VERSION="1.2.2"

echo ""
echo "📥 下载 nginx $NGINX_VERSION 和 nginx-rtmp-module..."
cd /tmp

if [ ! -f "nginx-${NGINX_VERSION}.tar.gz" ]; then
    wget http://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz
fi

if [ ! -d "nginx-rtmp-module" ]; then
    git clone https://github.com/arut/nginx-rtmp-module.git
    cd nginx-rtmp-module
    git checkout v${RTMP_MODULE_VERSION}
    cd ..
fi

echo ""
echo "🔧 编译 nginx + rtmp 模块..."
tar -zxvf nginx-${NGINX_VERSION}.tar.gz
cd nginx-${NGINX_VERSION}

./configure \
    --prefix=/usr/local/nginx \
    --with-http_ssl_module \
    --with-http_v2_module \
    --with-http_realip_module \
    --with-http_stub_status_module \
    --with-http_gzip_static_module \
    --with-pcre \
    --with-stream \
    --with-stream_ssl_module \
    --add-module=../nginx-rtmp-module

make -j$(nproc)
make install

echo ""
echo "📁 创建必要的目录..."
mkdir -p /var/www/hidrs/hls
mkdir -p /var/www/hidrs/dash
mkdir -p /var/www/hidrs/recordings
mkdir -p /var/www/hidrs/recordings/emergency
mkdir -p /var/log/nginx
mkdir -p /etc/nginx/ssl

# 设置权限
chmod -R 755 /var/www/hidrs
chown -R www-data:www-data /var/www/hidrs 2>/dev/null || chown -R nobody:nogroup /var/www/hidrs

echo ""
echo "📝 复制配置文件..."
HIDRS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cp "${HIDRS_DIR}/hidrs/config/nginx-rtmp.conf" /usr/local/nginx/conf/nginx.conf

echo ""
echo "🔐 生成自签名SSL证书（测试用）..."
if [ ! -f "/etc/nginx/ssl/broadcast.crt" ]; then
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/broadcast.key \
        -out /etc/nginx/ssl/broadcast.crt \
        -subj "/C=CN/ST=Beijing/L=Beijing/O=HIDRS/OU=Broadcast/CN=broadcast.hidrs.local"
    echo "✅ SSL证书已生成: /etc/nginx/ssl/broadcast.{crt,key}"
else
    echo "✅ SSL证书已存在"
fi

echo ""
echo "🚀 创建 systemd 服务..."
cat > /etc/systemd/system/nginx-rtmp.service <<EOF
[Unit]
Description=HIDRS RTMP Streaming Server
Documentation=http://nginx.org/en/docs/
After=network.target

[Service]
Type=forking
PIDFile=/var/run/nginx.pid
ExecStartPre=/usr/local/nginx/sbin/nginx -t -c /usr/local/nginx/conf/nginx.conf
ExecStart=/usr/local/nginx/sbin/nginx -c /usr/local/nginx/conf/nginx.conf
ExecReload=/bin/kill -s HUP \$MAINPID
ExecStop=/bin/kill -s QUIT \$MAINPID
PrivateTmp=true
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable nginx-rtmp.service

echo ""
echo "✅ nginx-rtmp 安装完成！"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📡 推流配置："
echo "   RTMP URL: rtmp://$(hostname -I | awk '{print $1}'):1935/live"
echo "   Stream Key: emergency?key=YOUR_KEY"
echo ""
echo "🎥 HLS播放地址："
echo "   HTTP: http://$(hostname -I | awk '{print $1}'):8080/hls/{stream_name}.m3u8"
echo "   HTTPS: https://$(hostname -I | awk '{print $1}'):8443/hls/{stream_name}.m3u8"
echo ""
echo "📊 统计页面："
echo "   http://$(hostname -I | awk '{print $1}'):8080/stat"
echo ""
echo "🔧 常用命令："
echo "   启动服务: systemctl start nginx-rtmp"
echo "   停止服务: systemctl stop nginx-rtmp"
echo "   重启服务: systemctl restart nginx-rtmp"
echo "   查看状态: systemctl status nginx-rtmp"
echo "   查看日志: tail -f /var/log/nginx/error.log"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

read -p "是否现在启动服务？ (Y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    systemctl start nginx-rtmp
    echo "✅ 服务已启动"
    systemctl status nginx-rtmp --no-pager
else
    echo "⏸️  稍后可手动启动: systemctl start nginx-rtmp"
fi

echo ""
echo "🎉 安装完成！现在可以使用 OBS 或 FFmpeg 推流了"
