"""
远程API连接器 - 用于连接外部存储系统
"""
import os
import requests
import logging
import json
import hashlib
from typing import Dict, Any, List, Tuple, Optional

# 设置日志
logger = logging.getLogger(__name__)

class RemoteAPIClient:
    """连接远程API的客户端"""
    
    def __init__(self, api_url: str = None):
        """初始化远程API客户端"""
        self.api_url = api_url or os.getenv('REMOTE_API', '')
        
        if not self.api_url:
            raise ValueError("未设置远程API地址")
            
        self.session = requests.Session()
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # 缓存相关
        self.use_cache = True
        self.cache_ttl = 3600  # 缓存有效期(秒)
        
        logger.info(f"远程API客户端已初始化: {self.api_url}")
    
    def _generate_cache_key(self, endpoint: str, params: Dict) -> str:
        """生成缓存键"""
        data = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(data.encode()).hexdigest()
    
    def search(self, query: Dict, limit: int = 10, skip: int = 0) -> Tuple[List, int]:
        """搜索远程API"""
        try:
            endpoint = "/search"
            params = {
                "query": query,
                "limit": limit,
                "skip": skip
            }
            
            # 发送请求
            response = self.session.post(
                f"{self.api_url}{endpoint}",
                headers=self.headers,
                json=params,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("data", []), data.get("total", 0)
            else:
                logger.error(f"远程API请求失败: {response.status_code} - {response.text}")
                return [], 0
                
        except Exception as e:
            logger.error(f"远程API搜索异常: {str(e)}")
            return [], 0
    
    def aggregate(self, agg_query: Dict) -> Dict:
        """聚合查询远程API"""
        try:
            endpoint = "/aggregate"
            
            # 发送请求
            response = self.session.post(
                f"{self.api_url}{endpoint}",
                headers=self.headers,
                json=agg_query,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get("aggregations", {})
            else:
                logger.error(f"远程API聚合请求失败: {response.status_code} - {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"远程API聚合异常: {str(e)}")
            return {}
    
    def get_file_content(self, file_path: str, line_number: int) -> Optional[Dict]:
        """获取远程文件的特定行内容"""
        try:
            endpoint = "/file/content"
            params = {
                "file_path": file_path,
                "line": line_number
            }
            
            # 发送请求
            response = self.session.post(
                f"{self.api_url}{endpoint}",
                headers=self.headers,
                json=params,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get("data")
            else:
                logger.error(f"获取远程文件内容失败: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"获取远程文件内容异常: {str(e)}")
            return None
    
    def get_stats(self) -> Dict:
        """获取远程系统统计信息"""
        try:
            endpoint = "/stats"
            
            # 发送请求
            response = self.session.get(
                f"{self.api_url}{endpoint}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json().get("data", {})
            else:
                logger.error(f"获取远程统计信息失败: {response.status_code} - {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"获取远程统计信息异常: {str(e)}")
            return {}