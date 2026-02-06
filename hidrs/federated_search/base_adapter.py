"""
搜索适配器基类 - 定义统一接口

所有搜索源必须实现此接口
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from enum import Enum


class AdapterType(Enum):
    """适配器类型"""
    CORE = 1      # 核心：HIDRS自己的索引（HLIG理论）
    FALLBACK = 2  # 降级：外部搜索源（Google/百度等）
    DATA = 3      # 数据：仅用于数据采集


class SearchAdapter(ABC):
    """搜索源适配器基类"""

    def __init__(self, name: str, adapter_type: AdapterType, priority: int):
        """
        初始化搜索适配器

        参数:
        - name: 适配器名称
        - adapter_type: 适配器类型（核心/降级/数据）
        - priority: 优先级（数字越小优先级越高）
                   核心适配器：1
                   降级适配器：2-10
                   数据采集：11+
        """
        self.name = name
        self.adapter_type = adapter_type
        self.priority = priority
        self._available = True
        self._last_error = None

    @abstractmethod
    def search(self, query: str, limit: int = 10, **kwargs) -> List[Dict]:
        """
        执行搜索

        参数:
        - query: 搜索查询
        - limit: 返回结果数量限制
        - kwargs: 额外参数

        返回:
        - 结果列表，每个结果为字典，包含以下字段：
          {
              'title': str,        # 标题
              'url': str,          # URL
              'snippet': str,      # 摘要
              'source': str,       # 来源（适配器名称）
              'timestamp': str,    # 时间戳（可选）
              'score': float,      # 相关性得分（可选）
              'metadata': dict     # 额外元数据（可选）
          }
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        检查服务是否可用

        返回:
        - True: 服务可用
        - False: 服务不可用
        """
        pass

    def get_priority(self) -> int:
        """获取优先级"""
        return self.priority

    def get_type(self) -> AdapterType:
        """获取适配器类型"""
        return self.adapter_type

    def is_core(self) -> bool:
        """是否为核心适配器"""
        return self.adapter_type == AdapterType.CORE

    def is_fallback(self) -> bool:
        """是否为降级适配器"""
        return self.adapter_type == AdapterType.FALLBACK

    def get_last_error(self) -> Optional[str]:
        """获取最后一次错误信息"""
        return self._last_error

    def mark_unavailable(self, error: str = None):
        """标记服务不可用"""
        self._available = False
        self._last_error = error

    def mark_available(self):
        """标记服务可用"""
        self._available = True
        self._last_error = None

    def health_check(self) -> bool:
        """
        健康检查（可选实现）

        返回:
        - True: 健康
        - False: 不健康
        """
        return self.is_available()

    def __repr__(self):
        return f"<{self.__class__.__name__}(name='{self.name}', type={self.adapter_type.name}, priority={self.priority}, available={self._available})>"
