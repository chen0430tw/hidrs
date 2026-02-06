"""
结果聚合器 - 使用全息映射聚合分布式计算结果

核心思想：
1. 每个节点产生局部结果
2. 使用全息映射将局部结果映射到全局
3. 聚合全局结果

全息映射理论：
H = Φ_hol(L_local) → L_global
局部信息 → 全局信息

聚合策略：
- MapReduce: Map（分散计算）+ Reduce（聚合结果）
- HLIG增强: 使用Fiedler向量加权聚合
"""
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AggregationType(Enum):
    """聚合类型"""
    SUM = "sum"              # 求和
    AVERAGE = "average"      # 平均
    MAX = "max"              # 最大值
    MIN = "min"              # 最小值
    CONCAT = "concat"        # 连接（列表/字符串）
    CUSTOM = "custom"        # 自定义函数


class ResultAggregator:
    """结果聚合器"""

    def __init__(
        self,
        use_hlig_weighting: bool = True
    ):
        """
        初始化结果聚合器

        参数:
        - use_hlig_weighting: 是否使用HLIG权重聚合
        """
        self.use_hlig_weighting = use_hlig_weighting

        # 注册的聚合函数
        self.aggregation_functions: Dict[str, Callable] = {
            AggregationType.SUM.value: self._aggregate_sum,
            AggregationType.AVERAGE.value: self._aggregate_average,
            AggregationType.MAX.value: self._aggregate_max,
            AggregationType.MIN.value: self._aggregate_min,
            AggregationType.CONCAT.value: self._aggregate_concat
        }

        logger.info("[ResultAggregator] 初始化完成")
        logger.info(f"  HLIG权重聚合: {'启用' if use_hlig_weighting else '禁用'}")

    def aggregate(
        self,
        results: List[Dict],
        aggregation_type: AggregationType = AggregationType.SUM,
        custom_func: Optional[Callable] = None,
        node_weights: Optional[Dict[str, float]] = None
    ) -> Any:
        """
        聚合结果

        参数:
        - results: 结果列表 [{'node_id': str, 'result': any}, ...]
        - aggregation_type: 聚合类型
        - custom_func: 自定义聚合函数（当aggregation_type=CUSTOM时使用）
        - node_weights: 节点权重字典 {node_id: weight}（用于HLIG加权）

        返回:
        - 聚合后的结果
        """
        if not results:
            logger.warning("[ResultAggregator] 没有结果需要聚合")
            return None

        logger.info(f"[ResultAggregator] 聚合 {len(results)} 个结果 (类型: {aggregation_type.value})")

        # 1. 提取结果数据
        result_values = [r['result'] for r in results if 'result' in r]

        if not result_values:
            logger.warning("[ResultAggregator] 所有结果都为空")
            return None

        # 2. 准备权重（如果使用HLIG加权）
        weights = None
        if self.use_hlig_weighting and node_weights:
            weights = [node_weights.get(r['node_id'], 1.0) for r in results if 'result' in r]
            # 归一化权重
            weights = np.array(weights)
            weights = weights / weights.sum()
            logger.debug(f"[ResultAggregator] 使用HLIG权重: {weights}")

        # 3. 执行聚合
        if aggregation_type == AggregationType.CUSTOM and custom_func:
            aggregated_result = custom_func(result_values, weights)
        else:
            agg_func = self.aggregation_functions.get(aggregation_type.value)
            if not agg_func:
                raise ValueError(f"未知的聚合类型: {aggregation_type}")
            aggregated_result = agg_func(result_values, weights)

        logger.info(f"[ResultAggregator] 聚合完成")

        return aggregated_result

    def _aggregate_sum(self, values: List, weights: Optional[np.ndarray] = None) -> Any:
        """求和聚合"""
        try:
            if weights is not None:
                # 加权求和
                return np.sum([v * w for v, w in zip(values, weights)])
            else:
                return np.sum(values)
        except Exception as e:
            logger.error(f"[ResultAggregator] 求和失败: {e}")
            return sum(values)  # 回退到Python内置sum

    def _aggregate_average(self, values: List, weights: Optional[np.ndarray] = None) -> float:
        """平均值聚合"""
        try:
            if weights is not None:
                # 加权平均
                return np.average(values, weights=weights)
            else:
                return np.mean(values)
        except Exception as e:
            logger.error(f"[ResultAggregator] 平均值计算失败: {e}")
            return sum(values) / len(values)

    def _aggregate_max(self, values: List, weights: Optional[np.ndarray] = None) -> Any:
        """最大值聚合（权重被忽略）"""
        return max(values)

    def _aggregate_min(self, values: List, weights: Optional[np.ndarray] = None) -> Any:
        """最小值聚合（权重被忽略）"""
        return min(values)

    def _aggregate_concat(self, values: List, weights: Optional[np.ndarray] = None) -> Any:
        """连接聚合"""
        if all(isinstance(v, list) for v in values):
            # 列表连接
            result = []
            for v in values:
                result.extend(v)
            return result
        elif all(isinstance(v, str) for v in values):
            # 字符串连接
            return ''.join(values)
        else:
            # 默认转为列表
            return list(values)

    def aggregate_with_hlig(
        self,
        results: List[Dict],
        fiedler_scores: Dict[str, float],
        aggregation_type: AggregationType = AggregationType.AVERAGE
    ) -> Any:
        """
        使用HLIG权重聚合结果

        参数:
        - results: 结果列表
        - fiedler_scores: Fiedler得分字典 {node_id: score}
        - aggregation_type: 聚合类型

        返回:
        - 加权聚合结果
        """
        logger.info("[ResultAggregator] 使用HLIG权重聚合")

        # 使用Fiedler得分作为权重
        node_weights = {
            node_id: abs(score)  # 使用绝对值作为权重
            for node_id, score in fiedler_scores.items()
        }

        return self.aggregate(
            results=results,
            aggregation_type=aggregation_type,
            node_weights=node_weights
        )

    def map_reduce(
        self,
        tasks: List,
        map_func: Callable,
        reduce_func: Callable,
        node_weights: Optional[Dict[str, float]] = None
    ) -> Any:
        """
        MapReduce模式聚合

        参数:
        - tasks: 任务列表
        - map_func: Map函数（应用到每个任务）
        - reduce_func: Reduce函数（聚合所有结果）
        - node_weights: 节点权重

        返回:
        - 聚合结果
        """
        logger.info(f"[ResultAggregator] MapReduce: {len(tasks)} 个任务")

        # Map阶段
        mapped_results = []
        for i, task in enumerate(tasks):
            try:
                result = map_func(task)
                mapped_results.append({
                    'task_index': i,
                    'result': result
                })
            except Exception as e:
                logger.error(f"[ResultAggregator] Map失败 (任务{i}): {e}")

        if not mapped_results:
            logger.warning("[ResultAggregator] Map阶段没有成功的结果")
            return None

        # Reduce阶段
        try:
            result_values = [r['result'] for r in mapped_results]

            # 准备权重
            weights = None
            if node_weights:
                weights = [node_weights.get(r.get('node_id', ''), 1.0) for r in mapped_results]
                weights = np.array(weights) / sum(weights)

            reduced_result = reduce_func(result_values, weights)
            logger.info("[ResultAggregator] Reduce完成")

            return reduced_result

        except Exception as e:
            logger.error(f"[ResultAggregator] Reduce失败: {e}")
            return None

    def holographic_aggregate(
        self,
        local_results: List[Dict],
        topology_matrix: np.ndarray
    ) -> Dict:
        """
        全息映射聚合

        使用拉普拉斯矩阵将局部结果映射到全局

        参数:
        - local_results: 局部结果列表 [{'node_id', 'result'}, ...]
        - topology_matrix: 拓扑矩阵（拉普拉斯矩阵）

        返回:
        - 全局聚合结果
        """
        try:
            from hidrs.holographic_mapping.holographic_mapper import HolographicMapper

            logger.info("[ResultAggregator] 使用全息映射聚合")

            # 1. 构建局部结果向量
            n = len(local_results)
            local_vector = np.array([r['result'] for r in local_results if isinstance(r['result'], (int, float))])

            if len(local_vector) != n:
                logger.warning("[ResultAggregator] 结果类型不一致，使用标准聚合")
                return {
                    'global_result': self.aggregate(local_results, AggregationType.AVERAGE),
                    'method': 'standard'
                }

            # 2. 应用全息映射
            mapper = HolographicMapper(dimension=n)
            global_vector = mapper.map_local_to_global(topology_matrix, local_vector)

            # 3. 聚合全局向量
            global_result = float(np.mean(global_vector))

            logger.info(f"[ResultAggregator] 全息映射完成: 局部均值={np.mean(local_vector):.4f}, 全局结果={global_result:.4f}")

            return {
                'global_result': global_result,
                'local_mean': float(np.mean(local_vector)),
                'global_vector': global_vector.tolist(),
                'method': 'holographic'
            }

        except Exception as e:
            logger.error(f"[ResultAggregator] 全息映射失败: {e}")
            # 回退到标准聚合
            return {
                'global_result': self.aggregate(local_results, AggregationType.AVERAGE),
                'method': 'fallback'
            }

    def register_custom_aggregation(self, name: str, func: Callable):
        """
        注册自定义聚合函数

        参数:
        - name: 函数名
        - func: 聚合函数 func(values: List, weights: Optional[np.ndarray]) -> Any
        """
        self.aggregation_functions[name] = func
        logger.info(f"[ResultAggregator] 注册自定义聚合函数: {name}")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'use_hlig_weighting': self.use_hlig_weighting,
            'registered_functions': list(self.aggregation_functions.keys())
        }


# 示例：自定义聚合函数

def weighted_variance(values: List[float], weights: Optional[np.ndarray] = None) -> float:
    """计算加权方差"""
    if weights is None:
        return float(np.var(values))

    mean = np.average(values, weights=weights)
    variance = np.average((values - mean) ** 2, weights=weights)
    return float(variance)


def consensus_result(values: List, weights: Optional[np.ndarray] = None, threshold: float = 0.5) -> Any:
    """
    共识结果：返回出现次数超过阈值的值

    用于分类任务的投票聚合
    """
    from collections import Counter

    if weights is None:
        weights = np.ones(len(values))

    # 加权计数
    weighted_counts = Counter()
    for value, weight in zip(values, weights):
        weighted_counts[value] += weight

    total_weight = sum(weights)
    most_common = weighted_counts.most_common(1)[0]

    if most_common[1] / total_weight >= threshold:
        return most_common[0]
    else:
        return None  # 没有达成共识
