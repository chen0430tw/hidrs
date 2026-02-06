"""
Common Crawl 查询引擎 - 类XKeyscore高级查询接口

功能：
1. 多条件复合查询（Query Builder）
2. 时间范围筛选
3. 域名/TLD筛选
4. 关键词全文搜索
5. 聚类分析（基于HLIG）
6. 时间线趋势分析

查询示例：
    engine = CommonCrawlQueryEngine()

    # 简单查询
    results = engine.search("网络攻击")

    # 高级查询
    results = engine.advanced_search(
        keywords=["网络攻击", "APT"],
        domain="*.gov.cn",
        from_date="2024-01-01",
        to_date="2024-12-31",
        status_codes=[200],
        limit=1000
    )

    # 聚类分析
    clusters = engine.cluster_results(results)
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urlparse
import re

try:
    from pymongo import MongoClient
except ImportError:
    raise ImportError("需要安装pymongo: pip install pymongo")

logger = logging.getLogger(__name__)


class CommonCrawlQueryEngine:
    """Common Crawl查询引擎"""

    def __init__(
        self,
        mongo_uri: str = 'mongodb://localhost:27017/',
        database: str = 'hidrs_commoncrawl',
        collection: str = 'web_pages',
    ):
        """
        初始化查询引擎

        Args:
            mongo_uri: MongoDB连接URI
            database: 数据库名
            collection: 集合名
        """
        try:
            self.client = MongoClient(mongo_uri)
            self.db = self.client[database]
            self.collection = self.db[collection]
            logger.info(f"✅ 查询引擎已连接: {database}.{collection}")
        except Exception as e:
            logger.error(f"MongoDB连接失败: {e}")
            raise

        # 尝试加载HLIG分析器
        try:
            from hidrs.laplacian_analyzer import LaplacianAnalyzer
            self.laplacian_analyzer = LaplacianAnalyzer()
            self.hlig_available = True
            logger.info("✅ HLIG分析器已加载")
        except ImportError:
            self.hlig_available = False
            logger.warning("⚠️ HLIG分析器未找到")

    def search(
        self,
        query: str,
        limit: int = 100,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        简单搜索（全文索引）

        Args:
            query: 搜索关键词
            limit: 返回数量
            skip: 跳过数量（分页）

        Returns:
            结果列表
        """
        logger.info(f"搜索: {query}")

        try:
            # 使用MongoDB全文索引
            cursor = self.collection.find(
                {'$text': {'$search': query}},
                {'score': {'$meta': 'textScore'}}
            ).sort(
                [('score', {'$meta': 'textScore'})]
            ).skip(skip).limit(limit)

            results = list(cursor)
            logger.info(f"找到 {len(results)} 条结果")

            return results

        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []

    def advanced_search(
        self,
        keywords: Optional[List[str]] = None,
        url: Optional[str] = None,
        domain: Optional[str] = None,
        tld: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        status_codes: Optional[List[int]] = None,
        content_types: Optional[List[str]] = None,
        limit: int = 1000,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        高级多条件查询（类XKeyscore Query Builder）

        Args:
            keywords: 关键词列表（AND逻辑）
            url: URL精确匹配或正则
            domain: 域名（支持通配符*）
            tld: 顶级域名（如.cn, .gov）
            from_date: 开始日期 YYYY-MM-DD
            to_date: 结束日期 YYYY-MM-DD
            status_codes: HTTP状态码列表
            content_types: MIME类型列表
            limit: 返回数量
            skip: 跳过数量

        Returns:
            结果列表
        """
        logger.info("执行高级查询")

        # 构建查询条件
        query = {'$and': []}

        # 1. 关键词搜索
        if keywords:
            for keyword in keywords:
                query['$and'].append({
                    '$or': [
                        {'keywords': {'$regex': keyword, '$options': 'i'}},
                        {'title': {'$regex': keyword, '$options': 'i'}},
                        {'text': {'$regex': keyword, '$options': 'i'}},
                    ]
                })

        # 2. URL匹配
        if url:
            if '*' in url:
                # 通配符转正则
                regex_pattern = url.replace('.', r'\.').replace('*', '.*')
                query['$and'].append({'url': {'$regex': regex_pattern}})
            else:
                query['$and'].append({'url': url})

        # 3. 域名匹配
        if domain:
            if '*' in domain:
                regex_pattern = domain.replace('.', r'\.').replace('*', '.*')
                query['$and'].append({'domain': {'$regex': regex_pattern}})
            else:
                query['$and'].append({'domain': domain})

        # 4. TLD匹配
        if tld:
            query['$and'].append({'domain': {'$regex': f'{re.escape(tld)}$'}})

        # 5. 时间范围
        if from_date or to_date:
            time_query = {}
            if from_date:
                time_query['$gte'] = datetime.fromisoformat(from_date)
            if to_date:
                time_query['$lte'] = datetime.fromisoformat(to_date)
            query['$and'].append({'timestamp': time_query})

        # 6. 状态码过滤
        if status_codes:
            query['$and'].append({'status_code': {'$in': status_codes}})

        # 7. Content-Type过滤
        if content_types:
            query['$and'].append({
                '$or': [
                    {'content_type': {'$regex': ct, '$options': 'i'}}
                    for ct in content_types
                ]
            })

        # 如果没有任何条件，返回全部
        if not query['$and']:
            query = {}

        # 执行查询
        try:
            cursor = self.collection.find(query).skip(skip).limit(limit)
            results = list(cursor)

            logger.info(
                f"高级查询完成: {len(results)} 条结果, "
                f"查询条件数: {len(query.get('$and', []))}"
            )

            return results

        except Exception as e:
            logger.error(f"高级查询失败: {e}")
            return []

    def cluster_results(
        self,
        results: List[Dict[str, Any]],
        n_clusters: int = 5,
    ) -> Dict[str, Any]:
        """
        对查询结果进行聚类分析（基于HLIG）

        Args:
            results: 查询结果
            n_clusters: 聚类数量

        Returns:
            聚类结果:
            {
                'clusters': [
                    {
                        'id': int,
                        'size': int,
                        'keywords': list,
                        'representative_urls': list,
                    }
                ],
                'similarity_matrix': ndarray,
            }
        """
        if not self.hlig_available:
            logger.warning("HLIG分析器不可用，返回简单分组")
            return self._simple_clustering(results, n_clusters)

        logger.info(f"执行HLIG聚类分析: {len(results)} 条记录")

        try:
            # TODO: 实现基于拉普拉斯谱的聚类
            # 这需要计算每个文档的拉普拉斯向量，然后进行谱聚类

            # 目前返回简单分组
            return self._simple_clustering(results, n_clusters)

        except Exception as e:
            logger.error(f"聚类分析失败: {e}")
            return {'clusters': [], 'error': str(e)}

    def _simple_clustering(
        self,
        results: List[Dict[str, Any]],
        n_clusters: int
    ) -> Dict[str, Any]:
        """简单的聚类（按域名分组）"""
        from collections import defaultdict

        domain_groups = defaultdict(list)

        for result in results:
            domain = result.get('domain', 'unknown')
            domain_groups[domain].append(result)

        # 取前n_clusters个最大的组
        sorted_groups = sorted(
            domain_groups.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )[:n_clusters]

        clusters = []
        for idx, (domain, items) in enumerate(sorted_groups):
            clusters.append({
                'id': idx,
                'domain': domain,
                'size': len(items),
                'representative_urls': [item['url'] for item in items[:5]],
            })

        return {'clusters': clusters}

    def get_timeline(
        self,
        query: Dict[str, Any],
        interval: str = 'day',
    ) -> List[Dict[str, Any]]:
        """
        获取时间线统计（时间趋势分析）

        Args:
            query: MongoDB查询条件
            interval: 时间间隔 (hour/day/week/month)

        Returns:
            时间线数据:
            [
                {'timestamp': datetime, 'count': int},
                ...
            ]
        """
        logger.info(f"生成时间线: interval={interval}")

        # MongoDB聚合管道
        date_format = {
            'hour': '%Y-%m-%d %H:00',
            'day': '%Y-%m-%d',
            'week': '%Y-W%U',
            'month': '%Y-%m',
        }.get(interval, '%Y-%m-%d')

        pipeline = [
            {'$match': query},
            {
                '$group': {
                    '_id': {
                        '$dateToString': {
                            'format': date_format,
                            'date': '$timestamp'
                        }
                    },
                    'count': {'$sum': 1}
                }
            },
            {'$sort': {'_id': 1}}
        ]

        try:
            results = list(self.collection.aggregate(pipeline))
            timeline = [
                {'timestamp': item['_id'], 'count': item['count']}
                for item in results
            ]

            logger.info(f"时间线生成完成: {len(timeline)} 个数据点")
            return timeline

        except Exception as e:
            logger.error(f"时间线生成失败: {e}")
            return []

    def get_domain_statistics(
        self,
        query: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        获取域名统计（Top域名）

        Args:
            query: 查询条件（可选）
            limit: 返回数量

        Returns:
            域名统计:
            [
                {'domain': str, 'count': int, 'percentage': float},
                ...
            ]
        """
        logger.info("生成域名统计")

        pipeline = []
        if query:
            pipeline.append({'$match': query})

        pipeline.extend([
            {
                '$group': {
                    '_id': '$domain',
                    'count': {'$sum': 1}
                }
            },
            {'$sort': {'count': -1}},
            {'$limit': limit}
        ])

        try:
            results = list(self.collection.aggregate(pipeline))

            # 计算百分比
            total = sum(item['count'] for item in results)
            stats = [
                {
                    'domain': item['_id'],
                    'count': item['count'],
                    'percentage': (item['count'] / total * 100) if total > 0 else 0
                }
                for item in results
            ]

            logger.info(f"域名统计完成: {len(stats)} 个域名")
            return stats

        except Exception as e:
            logger.error(f"域名统计失败: {e}")
            return []

    def close(self):
        """关闭连接"""
        if self.client:
            self.client.close()
            logger.info("查询引擎已关闭")
