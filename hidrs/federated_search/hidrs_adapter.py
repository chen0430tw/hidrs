"""
HIDRS内部搜索适配器 - 核心适配器

这是HIDRS的灵魂：
- 基于HLIG理论（拉普拉斯谱分析 + 全息映射）
- 使用Elasticsearch作为存储
- 结果必须经过Fiedler值重排序
- 优先级最高（Priority 1）
"""
import logging
from typing import List, Dict, Optional
from elasticsearch import Elasticsearch, exceptions as es_exceptions

from .base_adapter import SearchAdapter, AdapterType

logger = logging.getLogger(__name__)


class HIDRSAdapter(SearchAdapter):
    """HIDRS核心搜索适配器（基于HLIG理论）"""

    def __init__(
        self,
        es_client: Elasticsearch = None,
        es_url: str = "http://localhost:9200",
        index_name: str = "hidrs-index",
        topology_manager = None
    ):
        """
        初始化HIDRS搜索适配器

        参数:
        - es_client: Elasticsearch客户端实例
        - es_url: Elasticsearch URL
        - index_name: 索引名称
        - topology_manager: 拓扑管理器（用于HLIG分析）
        """
        super().__init__(
            name="HIDRS-Core",
            adapter_type=AdapterType.CORE,
            priority=1  # 最高优先级
        )

        # Elasticsearch客户端
        self.es_client = es_client or Elasticsearch([es_url])
        self.index_name = index_name

        # 拓扑管理器（用于HLIG分析）
        self.topology_manager = topology_manager

        # 健康检查
        self._check_health()

    def _check_health(self):
        """检查Elasticsearch健康状态"""
        try:
            health = self.es_client.cluster.health()
            if health['status'] in ['green', 'yellow']:
                self.mark_available()
                logger.info(f"[{self.name}] Elasticsearch健康检查通过")
            else:
                self.mark_unavailable(f"Elasticsearch状态: {health['status']}")
                logger.warning(f"[{self.name}] Elasticsearch状态异常: {health['status']}")
        except Exception as e:
            self.mark_unavailable(str(e))
            logger.error(f"[{self.name}] Elasticsearch连接失败: {e}")

    def search(self, query: str, limit: int = 10, use_hlig: bool = True, **kwargs) -> List[Dict]:
        """
        执行HIDRS核心搜索

        参数:
        - query: 搜索查询
        - limit: 返回结果数量
        - use_hlig: 是否使用HLIG重排序（默认True）
        - kwargs: 额外参数

        返回:
        - 搜索结果列表
        """
        if not self.is_available():
            logger.warning(f"[{self.name}] 服务不可用，跳过搜索")
            return []

        try:
            # 1. Elasticsearch基础搜索
            es_results = self._elasticsearch_search(query, limit * 2)  # 取更多结果用于重排序

            if not es_results:
                logger.info(f"[{self.name}] 未找到结果: {query}")
                return []

            # 2. HLIG重排序（这是HIDRS的核心！）
            if use_hlig and self.topology_manager:
                results = self._hlig_rerank(es_results, query)
            else:
                results = es_results

            # 3. 截取到指定数量
            return results[:limit]

        except es_exceptions.ConnectionError as e:
            self.mark_unavailable(f"Elasticsearch连接错误: {e}")
            logger.error(f"[{self.name}] 连接错误: {e}")
            return []
        except Exception as e:
            logger.error(f"[{self.name}] 搜索失败: {e}")
            return []

    def _elasticsearch_search(self, query: str, limit: int) -> List[Dict]:
        """
        执行Elasticsearch搜索

        使用多字段查询：
        - title (权重3)
        - content (权重2)
        - url (权重1)
        """
        try:
            # 构建查询
            es_query = {
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["title^3", "content^2", "url"],
                        "type": "best_fields",
                        "fuzziness": "AUTO"
                    }
                },
                "size": limit,
                "_source": ["title", "url", "content", "timestamp", "feature_vector"]
            }

            # 执行搜索
            response = self.es_client.search(
                index=self.index_name,
                body=es_query
            )

            # 解析结果
            results = []
            for hit in response['hits']['hits']:
                source = hit['_source']
                results.append({
                    'title': source.get('title', ''),
                    'url': source.get('url', ''),
                    'snippet': source.get('content', '')[:200],  # 前200字符作为摘要
                    'source': self.name,
                    'timestamp': source.get('timestamp'),
                    'score': hit['_score'],
                    'metadata': {
                        'es_score': hit['_score'],
                        'feature_vector': source.get('feature_vector'),  # 用于HLIG分析
                        'doc_id': hit['_id']
                    }
                })

            return results

        except Exception as e:
            logger.error(f"[{self.name}] Elasticsearch查询失败: {e}")
            raise

    def _hlig_rerank(self, results: List[Dict], query: str) -> List[Dict]:
        """
        使用HLIG理论重排序结果

        核心算法：
        1. 提取结果的特征向量
        2. 构建临时拉普拉斯矩阵
        3. 计算Fiedler向量
        4. 根据Fiedler向量分量对结果排序

        这是HIDRS区别于普通搜索引擎的关键！
        """
        try:
            import numpy as np
            from hidrs.network_topology.similarity_calculator import SimilarityCalculator
            from hidrs.network_topology.laplacian_matrix_calculator import LaplacianMatrixCalculator
            from hidrs.network_topology.spectral_analyzer import SpectralAnalyzer

            # 提取特征向量
            feature_vectors = []
            valid_results = []

            for result in results:
                fv = result.get('metadata', {}).get('feature_vector')
                if fv:
                    feature_vectors.append(np.array(fv))
                    valid_results.append(result)

            if len(feature_vectors) < 2:
                logger.warning(f"[{self.name}] 特征向量不足，跳过HLIG重排序")
                return results

            # 1. 构建相似度矩阵（邻接矩阵）
            similarity_calc = SimilarityCalculator(metric='cosine', threshold=0.5)
            W = similarity_calc.compute_similarity_matrix(feature_vectors)

            # 2. 构建拉普拉斯矩阵
            laplacian_calc = LaplacianMatrixCalculator(normalized=True)
            L = laplacian_calc.compute_laplacian(W)

            # 3. 计算Fiedler向量（这是HLIG的核心！）
            spectral = SpectralAnalyzer(use_sparse=True, k=10)
            fiedler_vector = spectral.compute_fiedler_vector(L)
            fiedler_value = spectral.compute_fiedler_value(L)

            logger.info(f"[{self.name}] HLIG分析: Fiedler值={fiedler_value:.6f}")

            # 4. 根据Fiedler向量重排序
            # Fiedler向量的分量反映了节点在网络中的重要性
            # 绝对值越大 = 越接近网络分割点 = 越重要
            for i, result in enumerate(valid_results):
                fiedler_score = abs(fiedler_vector[i])
                es_score = result.get('score', 0)

                # 融合Elasticsearch得分和Fiedler得分
                # Fiedler得分权重70%，ES得分权重30%
                result['final_score'] = 0.7 * fiedler_score + 0.3 * (es_score / 10.0)
                result['metadata']['fiedler_score'] = float(fiedler_score)
                result['metadata']['fiedler_value'] = float(fiedler_value)

            # 按最终得分排序
            valid_results.sort(key=lambda x: x['final_score'], reverse=True)

            logger.info(f"[{self.name}] HLIG重排序完成，返回 {len(valid_results)} 个结果")
            return valid_results

        except Exception as e:
            logger.error(f"[{self.name}] HLIG重排序失败: {e}")
            # 重排序失败时，返回原始结果
            return results

    def is_available(self) -> bool:
        """检查HIDRS服务是否可用"""
        if not self._available:
            # 尝试重新连接
            self._check_health()
        return self._available

    def get_index_stats(self) -> Dict:
        """获取索引统计信息"""
        try:
            stats = self.es_client.indices.stats(index=self.index_name)
            return {
                'total_docs': stats['_all']['primaries']['docs']['count'],
                'index_size': stats['_all']['primaries']['store']['size_in_bytes'],
                'available': True
            }
        except Exception as e:
            logger.error(f"[{self.name}] 获取统计信息失败: {e}")
            return {'available': False, 'error': str(e)}
