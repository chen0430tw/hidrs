"""
MongoDB索引创建脚本
根据ESR规则（Equality, Sort, Range）优化复合索引
性能优化：添加索引可提升查询速度10-1000倍
"""
import json
from pymongo import MongoClient, ASCENDING, DESCENDING


def create_search_logs_indexes(db):
    """为search_logs集合创建优化索引"""
    collection = db['search_logs']

    print("正在为 search_logs 集合创建索引...")

    # 索引1: timestamp降序索引（用于时间范围查询和排序）
    # 使用场景: get_search_stats中的时间范围查询
    collection.create_index(
        [('timestamp', DESCENDING)],
        name='idx_timestamp_desc',
        background=True
    )
    print("  ✓ 创建索引: idx_timestamp_desc")

    # 索引2: ESR规则复合索引（query_text + timestamp）
    # E (Equality): query_text 精确匹配
    # R (Range): timestamp 范围查询
    # 使用场景: 按查询文本分组统计，并限定时间范围
    collection.create_index(
        [('query_text', ASCENDING), ('timestamp', DESCENDING)],
        name='idx_query_text_timestamp',
        background=True
    )
    print("  ✓ 创建索引: idx_query_text_timestamp (ESR规则)")

    # 索引3: 用于查询空结果统计
    collection.create_index(
        [('results_count', ASCENDING), ('timestamp', DESCENDING)],
        name='idx_results_count_timestamp',
        background=True
    )
    print("  ✓ 创建索引: idx_results_count_timestamp")

    print("search_logs 索引创建完成！\n")


def create_topology_analysis_indexes(db):
    """为topology_analysis集合创建索引"""
    collection = db['topology_analysis']

    print("正在为 topology_analysis 集合创建索引...")

    # 索引: timestamp降序索引
    # 使用场景: api_server.py中查询历史Fiedler值
    collection.create_index(
        [('timestamp', DESCENDING)],
        name='idx_timestamp_desc',
        background=True
    )
    print("  ✓ 创建索引: idx_timestamp_desc")

    print("topology_analysis 索引创建完成！\n")


def create_feedback_indexes(db):
    """为decision_feedback集合创建索引"""
    collection = db['decision_feedback']

    print("正在为 decision_feedback 集合创建索引...")

    # 索引: timestamp降序索引（用于获取最新反馈）
    collection.create_index(
        [('timestamp', DESCENDING)],
        name='idx_timestamp_desc',
        background=True
    )
    print("  ✓ 创建索引: idx_timestamp_desc")

    print("decision_feedback 索引创建完成！\n")


def create_feature_vectors_indexes(db):
    """为feature_vectors集合创建索引"""
    collection = db['feature_vectors']

    print("正在为 feature_vectors 集合创建索引...")

    # 索引1: extraction_time索引（用于增量更新）
    collection.create_index(
        [('extraction_time', ASCENDING)],
        name='idx_extraction_time',
        background=True
    )
    print("  ✓ 创建索引: idx_extraction_time")

    # 索引2: original_id索引（用于查找特定文档）
    collection.create_index(
        [('original_id', ASCENDING)],
        name='idx_original_id',
        background=True,
        unique=True
    )
    print("  ✓ 创建索引: idx_original_id (唯一)")

    print("feature_vectors 索引创建完成！\n")


def list_indexes(db, collection_name):
    """列出集合的所有索引"""
    collection = db[collection_name]
    indexes = collection.list_indexes()

    print(f"\n{collection_name} 当前索引:")
    for idx in indexes:
        print(f"  - {idx['name']}: {idx['key']}")


def main():
    """主函数"""
    # 读取配置
    with open('config/realtime_search_config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 连接MongoDB
    print(f"连接到 MongoDB: {config['mongodb_uri']}")
    client = MongoClient(config['mongodb_uri'])
    db = client[config['mongodb_db']]

    print(f"数据库: {config['mongodb_db']}\n")
    print("=" * 60)

    # 创建所有索引
    try:
        create_search_logs_indexes(db)
        create_topology_analysis_indexes(db)
        create_feedback_indexes(db)
        create_feature_vectors_indexes(db)

        print("=" * 60)
        print("✅ 所有索引创建成功！")
        print("=" * 60)

        # 显示所有索引
        list_indexes(db, 'search_logs')
        list_indexes(db, 'topology_analysis')
        list_indexes(db, 'decision_feedback')
        list_indexes(db, 'feature_vectors')

        print("\n性能提升预期:")
        print("  • 时间范围查询: 10-100倍")
        print("  • 统计聚合查询: 50-500倍")
        print("  • 增量更新查询: 10-50倍")

    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        raise

    finally:
        client.close()


if __name__ == '__main__':
    main()
