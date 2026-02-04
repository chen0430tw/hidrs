#!/usr/bin/env python3
"""
HIDRS爬虫文件分析集成模块

将文件分析器集成到HIDRS的爬虫系统中，实现:
1. 自动分析爬取的文件
2. 将分析结果存储到MongoDB
3. 高风险文件警报
4. 文件安全过滤

作者: HIDRS Team
日期: 2026-02-04
"""

import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pymongo import MongoClient
from .file_analyzer import FileAnalyzer

logger = logging.getLogger(__name__)


class CrawlerFileAnalyzer:
    """
    爬虫文件分析器 - 集成HIDRS爬虫系统
    """

    def __init__(self, mongodb_uri: str = 'mongodb://localhost:27017/',
                 db_name: str = 'hidrs_db',
                 auto_delete_high_risk: bool = False):
        """
        初始化爬虫文件分析器

        Args:
            mongodb_uri: MongoDB连接URI
            db_name: 数据库名称
            auto_delete_high_risk: 是否自动删除高风险文件
        """
        self.client = MongoClient(mongodb_uri)
        self.db = self.client[db_name]
        self.file_analysis_collection = self.db['file_analysis']
        self.high_risk_alerts = self.db['high_risk_alerts']
        self.auto_delete_high_risk = auto_delete_high_risk

        # 创建索引
        self._create_indexes()

        logger.info(f"文件分析器已初始化 (DB: {db_name}, 自动删除高风险: {auto_delete_high_risk})")

    def _create_indexes(self):
        """
        创建MongoDB索引
        """
        # 文件分析索引
        self.file_analysis_collection.create_index([('file_path', 1)], unique=True)
        self.file_analysis_collection.create_index([('risk_level', 1), ('timestamp', -1)])
        self.file_analysis_collection.create_index([('hashes.sha256', 1)])

        # 高风险警报索引
        self.high_risk_alerts.create_index([('timestamp', -1)])
        self.high_risk_alerts.create_index([('file_path', 1)])

        logger.info("MongoDB索引已创建")

    def analyze_and_store(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        分析文件并存储结果到MongoDB

        Args:
            file_path: 文件路径
            metadata: 额外元数据 (爬虫来源、URL等)

        Returns:
            分析结果
        """
        try:
            # 分析文件
            logger.info(f"正在分析文件: {file_path}")
            analyzer = FileAnalyzer(file_path)
            result = analyzer.analyze()

            # 添加元数据
            result['file_path'] = file_path
            result['crawler_metadata'] = metadata or {}

            # 存储到MongoDB
            self.file_analysis_collection.update_one(
                {'file_path': file_path},
                {'$set': result},
                upsert=True
            )

            logger.info(f"文件分析完成: {file_path} (风险等级: {result['risk_assessment']['risk_level']})")

            # 高风险处理
            if result['risk_assessment']['risk_level'] in ['high', 'medium']:
                self._handle_high_risk_file(file_path, result)

            return result

        except Exception as e:
            logger.error(f"文件分析失败: {file_path} - {str(e)}")
            return {'error': str(e), 'file_path': file_path}

    def _handle_high_risk_file(self, file_path: str, analysis_result: Dict[str, Any]):
        """
        处理高风险文件
        """
        risk = analysis_result['risk_assessment']

        # 记录警报
        alert = {
            'file_path': file_path,
            'file_name': os.path.basename(file_path),
            'risk_level': risk['risk_level'],
            'risk_score': risk['risk_score'],
            'risk_factors': risk['risk_factors'],
            'recommendation': risk['recommendation'],
            'file_hash_sha256': analysis_result['hashes']['sha256'],
            'timestamp': datetime.now(),
            'handled': False,
            'action_taken': None
        }

        self.high_risk_alerts.insert_one(alert)
        logger.warning(f"⚠️ 高风险文件检测: {file_path} ({risk['risk_level']})")

        # 自动删除
        if self.auto_delete_high_risk and risk['risk_level'] == 'high':
            try:
                os.remove(file_path)
                logger.warning(f"🗑️ 高风险文件已删除: {file_path}")
                self.high_risk_alerts.update_one(
                    {'file_path': file_path},
                    {'$set': {'action_taken': 'deleted', 'handled': True}}
                )
            except Exception as e:
                logger.error(f"删除高风险文件失败: {file_path} - {str(e)}")

    def batch_analyze(self, file_paths: List[str], metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        批量分析文件

        Args:
            file_paths: 文件路径列表
            metadata: 公共元数据

        Returns:
            分析结果列表
        """
        results = []

        for file_path in file_paths:
            try:
                result = self.analyze_and_store(file_path, metadata)
                results.append(result)
            except Exception as e:
                logger.error(f"批量分析失败: {file_path} - {str(e)}")
                results.append({'error': str(e), 'file_path': file_path})

        logger.info(f"批量分析完成: {len(results)}/{len(file_paths)} 个文件")
        return results

    def get_high_risk_files(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取高风险文件列表

        Args:
            limit: 返回数量限制

        Returns:
            高风险文件列表
        """
        return list(self.high_risk_alerts.find().sort('timestamp', -1).limit(limit))

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取文件分析统计信息

        Returns:
            统计信息
        """
        pipeline = [
            {
                '$group': {
                    '_id': '$risk_assessment.risk_level',
                    'count': {'$sum': 1}
                }
            }
        ]

        risk_distribution = list(self.file_analysis_collection.aggregate(pipeline))

        return {
            'total_files_analyzed': self.file_analysis_collection.count_documents({}),
            'high_risk_alerts': self.high_risk_alerts.count_documents({}),
            'unhandled_alerts': self.high_risk_alerts.count_documents({'handled': False}),
            'risk_distribution': {item['_id']: item['count'] for item in risk_distribution},
            'last_updated': datetime.now().isoformat()
        }

    def query_by_hash(self, file_hash: str, hash_type: str = 'sha256') -> Optional[Dict[str, Any]]:
        """
        通过哈希值查询文件分析结果

        Args:
            file_hash: 文件哈希值
            hash_type: 哈希类型 (md5, sha1, sha256, sha512)

        Returns:
            分析结果或None
        """
        query_key = f'hashes.{hash_type}'
        return self.file_analysis_collection.find_one({query_key: file_hash})

    def close(self):
        """
        关闭数据库连接
        """
        self.client.close()
        logger.info("数据库连接已关闭")


def integrate_with_crawler(crawler_instance, mongodb_uri: str = 'mongodb://localhost:27017/',
                          auto_delete_high_risk: bool = False):
    """
    将文件分析器集成到爬虫实例

    Args:
        crawler_instance: 爬虫实例
        mongodb_uri: MongoDB连接URI
        auto_delete_high_risk: 是否自动删除高风险文件

    Returns:
        CrawlerFileAnalyzer实例
    """
    file_analyzer = CrawlerFileAnalyzer(mongodb_uri, auto_delete_high_risk=auto_delete_high_risk)

    # 获取爬虫的下载目录
    download_dir = getattr(crawler_instance, 'download_dir', './downloads')

    logger.info(f"文件分析器已集成到爬虫 (监控目录: {download_dir})")

    return file_analyzer


if __name__ == '__main__':
    # 测试集成
    logging.basicConfig(level=logging.INFO)

    analyzer = CrawlerFileAnalyzer()

    # 获取统计信息
    stats = analyzer.get_statistics()
    print("文件分析统计:")
    print(f"  总分析文件数: {stats['total_files_analyzed']}")
    print(f"  高风险警报数: {stats['high_risk_alerts']}")
    print(f"  未处理警报数: {stats['unhandled_alerts']}")
    print(f"  风险分布: {stats['risk_distribution']}")

    # 获取高风险文件
    high_risk_files = analyzer.get_high_risk_files(limit=10)
    if high_risk_files:
        print(f"\n最近{len(high_risk_files)}个高风险文件:")
        for alert in high_risk_files:
            print(f"  • {alert['file_name']} ({alert['risk_level']}) - {alert['timestamp']}")

    analyzer.close()
