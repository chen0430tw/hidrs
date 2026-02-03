#!/bin/bash

# 社工库ELK版启动脚本

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置
ES_INDEX="socialdb"
STORAGE_MODE="reference"
DATA_DIR="data"
LOGS_DIR="logs"
CONFIG_DIR="configs"

# 创建必要的目录
mkdir -p $DATA_DIR $LOGS_DIR $CONFIG_DIR

# 显示菜单
show_menu() {
    echo -e "${GREEN}===== 社工库ELK版 - 主菜单 =====${NC}"
    echo "1. 启动ELK环境 (Docker)"
    echo "2. 导入数据 (引用模式)"
    echo "3. 启动API服务"
    echo "4. 数据去重工具"
    echo "5. 系统状态"
    echo "0. 退出"
    echo -e "${GREEN}===============================${NC}"
    echo -n "请选择操作 [0-5]: "
}

# 启动ELK环境
start_elk() {
    echo -e "${YELLOW}启动ELK环境...${NC}"
    
    # 检查Docker是否安装
    if ! command -v docker >/dev/null 2>&1; then
        echo -e "${RED}错误: Docker未安装${NC}"
        return 1
    fi
    
    # 检查docker-compose是否安装
    if ! command -v docker-compose >/dev/null 2>&1; then
        echo -e "${RED}错误: Docker Compose未安装${NC}"
        return 1
    }
    
    # 启动ELK服务
    docker-compose up -d elasticsearch kibana logstash
    
    # 检查服务是否启动成功
    sleep 5
    if docker ps | grep -q elasticsearch && docker ps | grep -q kibana; then
        echo -e "${GREEN}ELK环境启动成功!${NC}"
        echo "Elasticsearch: http://localhost:9200"
        echo "Kibana: http://localhost:5601"
    else
        echo -e "${RED}ELK环境启动失败，请检查Docker日志${NC}"
        return 1
    fi
}

# 导入数据
import_data() {
    echo -e "${YELLOW}数据导入工具${NC}"
    
    # 请求文件路径
    echo -n "请输入数据文件或目录路径: "
    read data_path
    
    if [ ! -e "$data_path" ]; then
        echo -e "${RED}错误: 文件或目录不存在${NC}"
        return 1
    fi
    
    # 请求配置文件
    echo -n "请输入配置文件路径 (默认: configs/default.json): "
    read config_path
    
    if [ -z "$config_path" ]; then
        config_path="configs/default.json"
    fi
    
    if [ ! -f "$config_path" ]; then
        echo -e "${YELLOW}配置文件不存在，使用默认配置创建...${NC}"
        mkdir -p $(dirname "$config_path")
        cat > "$config_path" << EOF
{
    "split": "----",
    "fields": ["email", "password"],
    "custom_field": {
        "source": "default",
        "xtime": "202504"
    }
}
EOF
        echo -e "${GREEN}配置文件已创建: $config_path${NC}"
    fi
    
    # 导入命令参数
    if [ -f "$data_path" ]; then
        import_cmd="python backend/import_all.py -f \"$data_path\" -c \"$config_path\" --storage-mode $STORAGE_MODE --create-index"
    else
        import_cmd="python backend/import_all.py -d \"$data_path\" -c \"$config_path\" --storage-mode $STORAGE_MODE --create-index"
    fi
    
    # 执行导入
    echo -e "${YELLOW}开始导入数据...${NC}"
    echo "执行命令: $import_cmd"
    eval $import_cmd
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}数据导入完成!${NC}"
    else
        echo -e "${RED}数据导入出错，请查看日志${NC}"
        return 1
    fi
}

# 启动API服务
start_api() {
    echo -e "${YELLOW}启动API服务...${NC}"
    
    # 检查是否要使用Docker
    echo -n "使用Docker启动API? (y/n): "
    read use_docker
    
    if [[ $use_docker =~ ^[Yy]$ ]]; then
        # 使用Docker启动
        docker-compose up -d flask-api
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}API服务已启动!${NC}"
            echo "API地址: http://localhost:5000/api/test"
        else
            echo -e "${RED}API服务启动失败${NC}"
            return 1
        fi
    else
        # 直接启动Python脚本
        echo -e "${YELLOW}在新终端中启动API服务...${NC}"
        gnome-terminal -- bash -c "cd backend && python api_main.py; read -p '按Enter退出'"
        
        echo -e "${GREEN}API服务已启动!${NC}"
        echo "API地址: http://localhost:5000/api/test"
    fi
}

# 数据去重工具
dedup_tool() {
    echo -e "${YELLOW}数据去重工具${NC}"
    
    # 请求输入文件或目录
    echo -n "请输入源文件或目录: "
    read input_path
    
    if [ ! -e "$input_path" ]; then
        echo -e "${RED}错误: 文件或目录不存在${NC}"
        return 1
    fi
    
    # 请求输出路径
    echo -n "请输入输出文件或目录: "
    read output_path
    
    # 请求配置文件
    echo -n "请输入配置文件路径 (默认: configs/default.json): "
    read config_path
    
    if [ -z "$config_path" ]; then
        config_path="configs/default.json"
    fi
    
    if [ ! -f "$config_path" ]; then
        echo -e "${YELLOW}配置文件不存在，使用默认配置创建...${NC}"
        mkdir -p $(dirname "$config_path")
        cat > "$config_path" << EOF
{
    "split": "----",
    "fields": ["email", "password"],
    "custom_field": {
        "source": "default",
        "xtime": "202504"
    }
}
EOF
        echo -e "${GREEN}配置文件已创建: $config_path${NC}"
    fi
    
    # 请求去重键
    echo -n "去重依据字段 (默认: email, 选项: user, email, combine): "
    read dedup_key
    
    if [ -z "$dedup_key" ]; then
        dedup_key="email"
    fi
    
    # 构建命令
    if [ -f "$input_path" ]; then
        dedup_cmd="python backend/deduplicate.py -i \"$input_path\" -o \"$output_path\" -c \"$config_path\" -k $dedup_key"
    else
        dedup_cmd="python backend/deduplicate.py -d \"$input_path\" -o \"$output_path\" -c \"$config_path\" -k $dedup_key"
    fi
    
    # 执行去重
    echo -e "${YELLOW}开始数据去重...${NC}"
    echo "执行命令: $dedup_cmd"
    eval $dedup_cmd
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}数据去重完成!${NC}"
    else
        echo -e "${RED}数据去重出错，请查看日志${NC}"
        return 1
    fi
}

# 系统状态
system_status() {
    echo -e "${YELLOW}系统状态检查${NC}"
    
    # 检查Docker服务
    echo -e "${GREEN}Docker服务状态:${NC}"
    docker ps
    
    # 检查ES状态
    echo -e "\n${GREEN}Elasticsearch状态:${NC}"
    curl -s http://localhost:9200/_cluster/health?pretty || echo -e "${RED}Elasticsearch未运行${NC}"
    
    # 获取索引大小
    echo -e "\n${GREEN}索引大小:${NC}"
    curl -s http://localhost:9200/_cat/indices/$ES_INDEX* || echo -e "${RED}无法获取索引信息${NC}"
    
    # 获取API状态
    echo -e "\n${GREEN}API服务状态:${NC}"
    curl -s http://localhost:5000/api/test || echo -e "${RED}API服务未运行${NC}"
    
    # 获取存储模式和统计信息
    echo -e "\n${GREEN}系统配置:${NC}"
    echo "存储模式: $STORAGE_MODE"
    echo "数据目录: $DATA_DIR"
    
    # 显示磁盘空间
    echo -e "\n${GREEN}磁盘空间:${NC}"
    df -h
}

# 主循环
while true; do
    show_menu
    read choice
    
    case $choice in
        1)
            start_elk
            ;;
        2)
            import_data
            ;;
        3)
            start_api
            ;;
        4)
            dedup_tool
            ;;
        5)
            system_status
            ;;
        0)
            echo -e "${GREEN}退出程序，再见!${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}无效选择，请重试${NC}"
            ;;
    esac
    
    echo ""
    read -p "按Enter继续..."
    clear
done