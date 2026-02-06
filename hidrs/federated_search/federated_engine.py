"""
联邦搜索引擎 - 分层架构协调器

核心设计原则：
1. HIDRS Core（HLIG）是主搜索路径 - 这是船的龙骨
2. 外部源是降级层 - 这是应急方案，不是主体
3. 所有结果都经过HLIG重排序 - 保持HIDRS身份
4. 清晰的统计和监控 - 知道何时触发降级

忒修斯之船判断标准：
- 核心路径使用HLIG理论 ✅ → 还是HIDRS
- 外部源只是数据补充 ✅ → 还是HIDRS
- 外部源替代核心功能 ❌ → 变成搜索聚合器
"""
import logging
from typing import List, Dict, Optional
from .base_adapter import SearchAdapter
from .fallback_handler import FallbackHandler

logger = logging.getLogger(__name__)


class FederatedSearchEngine:
    """联邦搜索引擎 - 保持HIDRS核心纯粹"""

    def __init__(
        self,
        adapters: List[SearchAdapter],
        min_results_threshold: int = 3,
        enable_fallback: bool = True,
        always_use_hlig: bool = True
    ):
        """
        初始化联邦搜索引擎

        参数:
        - adapters: 搜索适配器列表
        - min_results_threshold: 最少结果阈值
        - enable_fallback: 是否启用降级（建议True）
        - always_use_hlig: 是否总是使用HLIG重排序（强制True保持身份）
        """
        self.adapters = adapters
        self.enable_fallback = enable_fallback
        self.always_use_hlig = always_use_hlig  # 忒修斯之船的锚点

        # 初始化降级处理器
        self.fallback_handler = FallbackHandler(
            adapters=adapters,
            min_results_threshold=min_results_threshold,
            enable_cascade=enable_fallback
        )

        # 获取核心适配器（用于HLIG重排序）
        self.core_adapter = self._get_core_adapter()

        logger.info(f"[FederatedSearchEngine] 初始化完成")
        logger.info(f"  降级功能: {'启用' if enable_fallback else '禁用'}")
        logger.info(f"  HLIG重排序: {'强制启用' if always_use_hlig else '可选'}")
        logger.info(f"  核心适配器: {self.core_adapter.name if self.core_adapter else '无'}")

    def _get_core_adapter(self) -> Optional[SearchAdapter]:
        """获取核心适配器"""
        for adapter in self.adapters:
            if adapter.is_core():
                return adapter
        logger.warning("[FederatedSearchEngine] 未找到核心适配器！")
        return None

    def search(self, query: str, limit: int = 10, force_core_only: bool = False) -> Dict:
        """
        执行联邦搜索

        参数:
        - query: 搜索查询
        - limit: 返回结果数量
        - force_core_only: 强制只使用核心适配器（不降级）

        返回:
        {
            'results': List[Dict],      # 搜索结果
            'source': str,              # 来源（core/fallback）
            'adapter_used': str,        # 使用的适配器
            'fallback_triggered': bool, # 是否触发降级
            'hlig_applied': bool,       # 是否应用了HLIG重排序
            'metadata': Dict            # 元数据
        }
        """
        logger.info(f"[FederatedSearchEngine] 搜索请求: '{query}' (limit={limit})")

        # 执行分层搜索
        search_result = self.fallback_handler.search(query, limit)

        results = search_result.get('results', [])
        source = search_result.get('source', 'unknown')
        fallback_triggered = search_result.get('fallback_triggered', False)

        # 关键判断：如果结果来自降级层，是否需要HLIG重排序？
        hlig_applied = False

        if self.always_use_hlig and results and source == 'fallback':
            # 即使结果来自外部源，也要用HLIG重排序
            # 这是保持HIDRS身份的关键！
            logger.info(f"[FederatedSearchEngine] 降级结果需要HLIG重排序...")
            results = self._apply_hlig_to_fallback_results(results, query)
            hlig_applied = True
            logger.info(f"[FederatedSearchEngine] ✅ HLIG重排序完成，保持HIDRS核心身份")

        elif source == 'core':
            # 核心结果本身就包含HLIG分析
            hlig_applied = True

        # 构建返回结果
        return {
            'results': results,
            'source': source,
            'adapter_used': search_result.get('adapter_used', 'unknown'),
            'fallback_triggered': fallback_triggered,
            'hlig_applied': hlig_applied,  # 关键标识
            'metadata': {
                'query': query,
                'total_results': len(results),
                'stats': search_result.get('stats', {}),
                'identity_preserved': hlig_applied  # 忒修斯之船的判断标准
            }
        }

    def _apply_hlig_to_fallback_results(self, results: List[Dict], query: str) -> List[Dict]:
        """
        对降级结果应用HLIG重排序

        这是关键函数：即使结果来自Google/百度，
        也要用HLIG理论重新排序，保持HIDRS身份！
        """
        try:
            if not self.core_adapter:
                logger.warning("[FederatedSearchEngine] 无核心适配器，无法应用HLIG")
                return results

            # 提取文本并向量化
            from sentence_transformers import SentenceTransformer
            import numpy as np

            logger.info(f"[FederatedSearchEngine] 向量化 {len(results)} 个降级结果...")

            encoder = SentenceTransformer('all-MiniLM-L6-v2')
            texts = [f"{r.get('title', '')} {r.get('snippet', '')}" for r in results]
            embeddings = encoder.encode(texts)

            # 应用HLIG重排序（和HIDRSAdapter._hlig_rerank相同逻辑）
            from hidrs.network_topology.similarity_calculator import SimilarityCalculator
            from hidrs.network_topology.laplacian_matrix_calculator import LaplacianMatrixCalculator
            from hidrs.network_topology.spectral_analyzer import SpectralAnalyzer

            # 1. 构建相似度矩阵
            similarity_calc = SimilarityCalculator(metric='cosine', threshold=0.5)
            W = similarity_calc.compute_similarity_matrix(embeddings.tolist())

            # 2. 构建拉普拉斯矩阵
            laplacian_calc = LaplacianMatrixCalculator(normalized=True)
            L = laplacian_calc.compute_laplacian(W)

            # 3. 计算Fiedler向量
            spectral = SpectralAnalyzer(use_sparse=True, k=10)
            fiedler_vector = spectral.compute_fiedler_vector(L)
            fiedler_value = spectral.compute_fiedler_value(L)

            logger.info(f"[FederatedSearchEngine] HLIG分析完成: Fiedler值={fiedler_value:.6f}")

            # 4. 重排序
            for i, result in enumerate(results):
                fiedler_score = abs(fiedler_vector[i])
                original_score = result.get('score', 0.5)

                # 融合原始得分和Fiedler得分
                result['final_score'] = 0.7 * fiedler_score + 0.3 * original_score
                result['metadata'] = result.get('metadata', {})
                result['metadata'].update({
                    'fiedler_score': float(fiedler_score),
                    'fiedler_value': float(fiedler_value),
                    'hlig_reranked': True,
                    'original_score': original_score
                })

            # 按最终得分排序
            results.sort(key=lambda x: x['final_score'], reverse=True)

            logger.info(f"[FederatedSearchEngine] ✅ HLIG重排序完成")
            return results

        except Exception as e:
            logger.error(f"[FederatedSearchEngine] HLIG重排序失败: {e}")
            logger.warning(f"[FederatedSearchEngine] 返回原始降级结果（未经HLIG处理）")
            # 失败时返回原始结果
            return results

    def get_system_status(self) -> Dict:
        """
        获取系统状态

        包含忒修斯之船的判断指标
        """
        health = self.fallback_handler.get_health_status()
        stats = health.get('stats', {})

        # 计算HIDRS身份纯度
        # 如果核心成功率高，说明HIDRS身份纯粹
        core_success_rate = stats.get('core_success_rate', 0)
        fallback_rate = stats.get('fallback_rate', 0)

        # 身份纯度 = (核心成功率 * 100) - (降级率 * 50)
        identity_purity = (core_success_rate * 100) - (fallback_rate * 50)
        identity_purity = max(0, min(100, identity_purity))  # 限制在0-100

        return {
            'health': health,
            'identity_analysis': {
                'core_success_rate': core_success_rate,
                'fallback_rate': fallback_rate,
                'identity_purity': identity_purity,  # 0-100，越高越纯粹
                'still_hidrs': identity_purity >= 50,  # 判断标准：>50% = 仍是HIDRS
                'judgment': self._get_identity_judgment(identity_purity)
            },
            'configuration': {
                'fallback_enabled': self.enable_fallback,
                'always_use_hlig': self.always_use_hlig,
                'core_adapter': self.core_adapter.name if self.core_adapter else None
            }
        }

    def _get_identity_judgment(self, purity: float) -> str:
        """
        忒修斯之船的判断

        根据身份纯度判断系统是否仍是HIDRS
        """
        if purity >= 90:
            return "✅ 纯粹的HIDRS - 核心路径主导，身份完整"
        elif purity >= 70:
            return "✅ HIDRS - 核心功能为主，偶尔降级"
        elif purity >= 50:
            return "⚠️ HIDRS - 降级较频繁，但仍保持HLIG核心"
        elif purity >= 30:
            return "⚠️ 混合系统 - HIDRS和外部源并重，身份模糊"
        else:
            return "❌ 搜索聚合器 - 主要依赖外部源，HIDRS身份已稀释"

    def health_check(self) -> bool:
        """健康检查"""
        if not self.core_adapter:
            return False
        return self.core_adapter.is_available()

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self.fallback_handler._get_current_stats()
