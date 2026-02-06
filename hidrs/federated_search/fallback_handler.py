"""
降级处理器 - 故障转移策略

设计原则：
1. 默认只使用HIDRS Core（HLIG理论）
2. 仅在Core失败时才启用外部源
3. 外部源结果也要经过HLIG重排序
4. 保持HIDRS的核心身份

降级策略：
    尝试HIDRS Core
        ↓ 失败/结果不足
    尝试次级源（按优先级）
        ↓ 仍然失败
    返回空结果或缓存结果
"""
import logging
from typing import List, Dict, Optional
from .base_adapter import SearchAdapter, AdapterType

logger = logging.getLogger(__name__)


class FallbackHandler:
    """降级处理器"""

    def __init__(
        self,
        adapters: List[SearchAdapter],
        min_results_threshold: int = 3,
        enable_cascade: bool = True
    ):
        """
        初始化降级处理器

        参数:
        - adapters: 搜索适配器列表
        - min_results_threshold: 最少结果阈值（低于此值则降级）
        - enable_cascade: 是否启用级联降级
        """
        # 按优先级排序适配器
        self.adapters = sorted(adapters, key=lambda x: x.get_priority())

        # 分离核心适配器和降级适配器
        self.core_adapters = [a for a in self.adapters if a.is_core()]
        self.fallback_adapters = [a for a in self.adapters if a.is_fallback()]

        self.min_results_threshold = min_results_threshold
        self.enable_cascade = enable_cascade

        # 统计信息
        self.stats = {
            'total_searches': 0,
            'core_success': 0,
            'fallback_used': 0,
            'total_failures': 0
        }

        logger.info(f"[FallbackHandler] 初始化完成")
        logger.info(f"  核心适配器: {[a.name for a in self.core_adapters]}")
        logger.info(f"  降级适配器: {[a.name for a in self.fallback_adapters]}")

    def search(self, query: str, limit: int = 10) -> Dict:
        """
        执行分层搜索

        返回:
        {
            'results': List[Dict],     # 搜索结果
            'source': str,             # 结果来源（core/fallback）
            'adapter_used': str,       # 使用的适配器名称
            'fallback_triggered': bool,# 是否触发了降级
            'stats': Dict              # 统计信息
        }
        """
        self.stats['total_searches'] += 1

        # Phase 1: 尝试核心适配器（HIDRS Core）
        logger.info(f"[FallbackHandler] 开始搜索: {query}")
        logger.info(f"[FallbackHandler] Phase 1: 尝试核心适配器...")

        core_results = self._try_core_adapters(query, limit)

        if core_results and len(core_results) >= self.min_results_threshold:
            # 核心适配器成功
            self.stats['core_success'] += 1
            logger.info(f"[FallbackHandler] ✅ 核心适配器成功返回 {len(core_results)} 个结果")

            return {
                'results': core_results,
                'source': 'core',
                'adapter_used': self.core_adapters[0].name if self.core_adapters else 'unknown',
                'fallback_triggered': False,
                'stats': self._get_current_stats()
            }

        # Phase 2: 核心失败，启用降级
        logger.warning(f"[FallbackHandler] ⚠️ 核心适配器失败或结果不足（{len(core_results) if core_results else 0}个）")
        logger.info(f"[FallbackHandler] Phase 2: 启动降级策略...")

        if not self.enable_cascade:
            logger.warning(f"[FallbackHandler] 级联降级已禁用，返回核心结果")
            return {
                'results': core_results or [],
                'source': 'core',
                'adapter_used': self.core_adapters[0].name if self.core_adapters else 'unknown',
                'fallback_triggered': False,
                'stats': self._get_current_stats()
            }

        fallback_results = self._try_fallback_adapters(query, limit)

        if fallback_results:
            self.stats['fallback_used'] += 1
            logger.info(f"[FallbackHandler] ✅ 降级适配器返回 {len(fallback_results['results'])} 个结果")

            return {
                **fallback_results,
                'fallback_triggered': True,
                'stats': self._get_current_stats()
            }

        # Phase 3: 所有适配器都失败
        self.stats['total_failures'] += 1
        logger.error(f"[FallbackHandler] ❌ 所有搜索适配器均失败")

        return {
            'results': [],
            'source': 'none',
            'adapter_used': 'none',
            'fallback_triggered': True,
            'error': '所有搜索源均不可用',
            'stats': self._get_current_stats()
        }

    def _try_core_adapters(self, query: str, limit: int) -> Optional[List[Dict]]:
        """尝试核心适配器"""
        for adapter in self.core_adapters:
            if not adapter.is_available():
                logger.warning(f"[FallbackHandler] 核心适配器 {adapter.name} 不可用，跳过")
                continue

            try:
                logger.info(f"[FallbackHandler] 尝试核心适配器: {adapter.name}")
                results = adapter.search(query, limit)

                if results:
                    logger.info(f"[FallbackHandler] 核心适配器 {adapter.name} 返回 {len(results)} 个结果")
                    return results
                else:
                    logger.warning(f"[FallbackHandler] 核心适配器 {adapter.name} 未返回结果")

            except Exception as e:
                logger.error(f"[FallbackHandler] 核心适配器 {adapter.name} 异常: {e}")
                adapter.mark_unavailable(str(e))
                continue

        return None

    def _try_fallback_adapters(self, query: str, limit: int) -> Optional[Dict]:
        """尝试降级适配器"""
        for adapter in self.fallback_adapters:
            if not adapter.is_available():
                logger.warning(f"[FallbackHandler] 降级适配器 {adapter.name} 不可用，跳过")
                continue

            try:
                logger.info(f"[FallbackHandler] 尝试降级适配器: {adapter.name}")
                results = adapter.search(query, limit)

                if results and len(results) >= self.min_results_threshold:
                    logger.info(f"[FallbackHandler] 降级适配器 {adapter.name} 返回 {len(results)} 个结果")

                    return {
                        'results': results,
                        'source': 'fallback',
                        'adapter_used': adapter.name
                    }
                else:
                    logger.warning(f"[FallbackHandler] 降级适配器 {adapter.name} 结果不足（{len(results) if results else 0}个）")

            except Exception as e:
                logger.error(f"[FallbackHandler] 降级适配器 {adapter.name} 异常: {e}")
                adapter.mark_unavailable(str(e))
                continue

        return None

    def _get_current_stats(self) -> Dict:
        """获取当前统计信息"""
        total = self.stats['total_searches']
        if total == 0:
            return {**self.stats, 'core_success_rate': 0.0, 'fallback_rate': 0.0}

        return {
            **self.stats,
            'core_success_rate': self.stats['core_success'] / total,
            'fallback_rate': self.stats['fallback_used'] / total,
            'failure_rate': self.stats['total_failures'] / total
        }

    def get_health_status(self) -> Dict:
        """获取所有适配器的健康状态"""
        return {
            'core_adapters': [
                {
                    'name': a.name,
                    'available': a.is_available(),
                    'last_error': a.get_last_error()
                }
                for a in self.core_adapters
            ],
            'fallback_adapters': [
                {
                    'name': a.name,
                    'available': a.is_available(),
                    'last_error': a.get_last_error()
                }
                for a in self.fallback_adapters
            ],
            'stats': self._get_current_stats()
        }

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'total_searches': 0,
            'core_success': 0,
            'fallback_used': 0,
            'total_failures': 0
        }
        logger.info("[FallbackHandler] 统计信息已重置")
