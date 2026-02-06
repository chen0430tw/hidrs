"""
联邦搜索模块 - 分层架构设计

核心原则：
1. HIDRS Core（HLIG理论）是主要搜索路径
2. 外部源（Google/百度/Archive）仅作为降级层
3. 所有结果都必须经过HLIG谱分析重排序
4. 保持HIDRS身份的纯粹性

架构：
    用户查询
        ↓
    HIDRS Core (HLIG)  ← 默认路径
        ↓ (失败时)
    Fallback Layer     ← 降级层
        ↓
    HLIG重排序         ← 保持核心
        ↓
    返回结果
"""

from .base_adapter import SearchAdapter, AdapterType
from .hidrs_adapter import HIDRSAdapter
from .google_adapter import GoogleSearchAdapter
from .baidu_adapter import BaiduSearchAdapter
from .archive_adapter import ArchiveSearchAdapter
from .fallback_handler import FallbackHandler
from .federated_engine import FederatedSearchEngine
from .faiss_index import FAISSVectorIndex, create_faiss_index, FAISS_AVAILABLE
from .hlig_optimizer import HLIGOptimizer, get_hlig_optimizer

__all__ = [
    'SearchAdapter',
    'AdapterType',
    'HIDRSAdapter',
    'GoogleSearchAdapter',
    'BaiduSearchAdapter',
    'ArchiveSearchAdapter',
    'FallbackHandler',
    'FederatedSearchEngine',
    'FAISSVectorIndex',
    'create_faiss_index',
    'FAISS_AVAILABLE',
    'HLIGOptimizer',
    'get_hlig_optimizer'
]
