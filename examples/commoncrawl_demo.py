"""
HIDRS Common Crawl 接入系统演示

功能展示：
1. 流式WARC文件解析
2. Common Crawl索引搜索
3. MongoDB数据导入
4. 高级多条件查询
5. HLIG聚类分析
6. 时间线趋势分析

使用前准备：
1. 安装依赖: pip install warcio comcrawl pymongo beautifulsoup4
2. 启动MongoDB: docker run -d -p 27017:27017 mongo
3. 运行演示: python examples/commoncrawl_demo.py
"""

import logging
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from hidrs.commoncrawl import (
    CommonCrawlIndexClient,
    WARCStreamParser,
    CommonCrawlImporter,
    CommonCrawlQueryEngine,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def demo_1_index_search():
    """演示1: 搜索Common Crawl索引"""
    print("\n" + "="*60)
    print("演示1: 搜索Common Crawl索引")
    print("="*60)

    client = CommonCrawlIndexClient()

    # 搜索Wikipedia相关页面
    print("\n搜索: *.wikipedia.org/*")
    results = client.search(
        url_pattern='*.wikipedia.org/*',
        limit=10,
        filter_status=[200],
    )

    print(f"\n找到 {len(results)} 个结果:")
    for idx, result in enumerate(results[:5], 1):
        print(f"{idx}. {result['url']}")
        print(f"   时间: {result['timestamp']}")
        print(f"   WARC: {result['filename']}")


def demo_2_stream_warc():
    """演示2: 流式解析WARC文件"""
    print("\n" + "="*60)
    print("演示2: 流式解析WARC文件（小样本）")
    print("="*60)

    # 首先获取一个WARC文件URL
    client = CommonCrawlIndexClient()
    results = client.search('*.example.com/*', limit=1)

    if not results:
        print("⚠️ 未找到示例数据，跳过此演示")
        return

    warc_url = client.get_warc_url(results[0]['filename'])
    print(f"\nWARC URL: {warc_url}")

    # 流式解析（只处理前3条记录）
    parser = WARCStreamParser()
    count = 0

    print("\n开始流式解析...")
    for record in parser.stream_warc(warc_url):
        count += 1
        print(f"\n记录 {count}:")
        print(f"  URL: {record['url']}")
        print(f"  标题: {record['title']}")
        print(f"  文本长度: {len(record['text'])} 字符")
        print(f"  链接数: {len(record['links'])}")

        if count >= 3:  # 只演示前3条
            break

    print(f"\n✅ 流式解析完成，处理了 {count} 条记录")


def demo_3_import_data():
    """演示3: 导入数据到MongoDB（小规模测试）"""
    print("\n" + "="*60)
    print("演示3: 导入数据到MongoDB")
    print("="*60)

    try:
        importer = CommonCrawlImporter(
            mongo_uri='mongodb://localhost:27017/',
            database='hidrs_commoncrawl_demo',
            collection='web_pages',
            batch_size=100,
        )

        # 导入少量数据（测试用）
        print("\n导入 example.com 相关页面（limit=50）...")
        stats = importer.import_from_url_pattern(
            url_pattern='*.example.com/*',
            limit=50,
        )

        print("\n✅ 导入完成!")
        print(f"  总记录数: {stats['total_records']}")
        print(f"  插入记录: {stats['inserted']}")
        print(f"  跳过记录: {stats['skipped']}")
        print(f"  失败记录: {stats['failed']}")
        print(f"  处理速度: {stats['records_per_second']:.2f} records/sec")

        # 获取集合统计
        coll_stats = importer.get_collection_stats()
        print("\n数据库统计:")
        print(f"  总文档数: {coll_stats['total_documents']}")
        print(f"  唯一域名: {coll_stats['unique_domains']}")
        print(f"  存储大小: {coll_stats['storage_size_mb']:.2f} MB")

        importer.close()

    except Exception as e:
        print(f"⚠️ 导入失败: {e}")
        print("  请确保MongoDB正在运行: docker run -d -p 27017:27017 mongo")


def demo_4_advanced_query():
    """演示4: 高级多条件查询"""
    print("\n" + "="*60)
    print("演示4: 高级多条件查询（类XKeyscore）")
    print("="*60)

    try:
        engine = CommonCrawlQueryEngine(
            mongo_uri='mongodb://localhost:27017/',
            database='hidrs_commoncrawl_demo',
            collection='web_pages',
        )

        # 简单搜索
        print("\n[查询1] 简单搜索: 'example'")
        results = engine.search('example', limit=5)
        print(f"找到 {len(results)} 条结果")

        # 高级搜索
        print("\n[查询2] 高级搜索: 域名=*.example.com, 状态码=200")
        results = engine.advanced_search(
            domain='*.example.com',
            status_codes=[200],
            limit=10,
        )
        print(f"找到 {len(results)} 条结果")
        for idx, result in enumerate(results[:3], 1):
            print(f"{idx}. {result['url']}")
            print(f"   标题: {result.get('title', 'N/A')}")

        # 域名统计
        print("\n[统计] Top域名分布:")
        domain_stats = engine.get_domain_statistics(limit=10)
        for idx, stat in enumerate(domain_stats[:5], 1):
            print(f"{idx}. {stat['domain']}: {stat['count']} ({stat['percentage']:.1f}%)")

        engine.close()

    except Exception as e:
        print(f"⚠️ 查询失败: {e}")
        print("  请先运行演示3导入数据")


def demo_5_clustering():
    """演示5: 聚类分析"""
    print("\n" + "="*60)
    print("演示5: 聚类分析（基于HLIG）")
    print("="*60)

    try:
        engine = CommonCrawlQueryEngine(
            mongo_uri='mongodb://localhost:27017/',
            database='hidrs_commoncrawl_demo',
            collection='web_pages',
        )

        # 查询结果
        results = engine.search('example', limit=50)

        if not results:
            print("⚠️ 无数据，请先运行演示3")
            return

        # 聚类分析
        print(f"\n对 {len(results)} 条结果进行聚类...")
        clusters = engine.cluster_results(results, n_clusters=5)

        print(f"\n✅ 聚类完成，共 {len(clusters['clusters'])} 个簇:")
        for cluster in clusters['clusters']:
            print(f"\n簇 {cluster['id']}:")
            print(f"  域名: {cluster['domain']}")
            print(f"  大小: {cluster['size']} 条记录")
            print(f"  代表URL:")
            for url in cluster['representative_urls'][:3]:
                print(f"    - {url}")

        engine.close()

    except Exception as e:
        print(f"⚠️ 聚类失败: {e}")


def demo_6_full_workflow():
    """演示6: 完整工作流（真实使用场景）"""
    print("\n" + "="*60)
    print("演示6: 完整工作流 - 追踪网络安全事件")
    print("="*60)

    scenario = """
    场景：追踪某个APT组织的C2服务器历史

    步骤：
    1. 搜索已知的C2域名模式
    2. 导入相关网页到MongoDB
    3. 分析时间线（何时活跃）
    4. 聚类分析（发现关联域名）
    5. 提取IOC（IP、域名、URL）
    """
    print(scenario)

    # 模拟APT C2域名
    c2_pattern = "*.suspicious-domain.com/*"

    print(f"\n步骤1: 搜索C2域名: {c2_pattern}")
    client = CommonCrawlIndexClient()
    index_results = client.search(c2_pattern, limit=20)
    print(f"  找到 {len(index_results)} 个历史记录")

    if not index_results:
        print("  ⚠️ 未找到数据（域名可能不存在于Common Crawl）")
        return

    print("\n步骤2: 导入数据到MongoDB...")
    try:
        importer = CommonCrawlImporter(
            database='hidrs_commoncrawl_demo',
            collection='apt_c2_pages',
        )
        stats = importer.import_from_url_pattern(c2_pattern, limit=20)
        print(f"  ✅ 导入完成: {stats['inserted']} 条记录")

        print("\n步骤3: 分析时间线...")
        engine = CommonCrawlQueryEngine(
            database='hidrs_commoncrawl_demo',
            collection='apt_c2_pages',
        )
        timeline = engine.get_timeline({'domain': {'$regex': 'suspicious-domain.com'}})
        print(f"  发现 {len(timeline)} 个时间点活跃")
        for point in timeline[:3]:
            print(f"    {point['timestamp']}: {point['count']} 次")

        print("\n步骤4: 聚类分析...")
        results = engine.advanced_search(domain='*.suspicious-domain.com', limit=50)
        clusters = engine.cluster_results(results)
        print(f"  识别出 {len(clusters['clusters'])} 个C2集群")

        print("\n步骤5: 提取IOC...")
        unique_domains = set(r['domain'] for r in results)
        print(f"  发现 {len(unique_domains)} 个唯一域名")
        for domain in list(unique_domains)[:5]:
            print(f"    - {domain}")

        print("\n✅ 威胁情报收集完成!")

        importer.close()
        engine.close()

    except Exception as e:
        print(f"  ⚠️ 工作流失败: {e}")


def main():
    """主函数"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║    HIDRS Common Crawl 接入系统 - 演示程序                      ║
║    类XKeyscore功能 + HLIG理论 + 30-50亿网页搜索              ║
╚══════════════════════════════════════════════════════════════╝
    """)

    print("选择演示:")
    print("  1. 搜索Common Crawl索引")
    print("  2. 流式解析WARC文件")
    print("  3. 导入数据到MongoDB")
    print("  4. 高级多条件查询")
    print("  5. 聚类分析（HLIG）")
    print("  6. 完整工作流（威胁情报）")
    print("  0. 运行所有演示")

    try:
        choice = input("\n请选择 (0-6): ").strip()

        if choice == '1':
            demo_1_index_search()
        elif choice == '2':
            demo_2_stream_warc()
        elif choice == '3':
            demo_3_import_data()
        elif choice == '4':
            demo_4_advanced_query()
        elif choice == '5':
            demo_5_clustering()
        elif choice == '6':
            demo_6_full_workflow()
        elif choice == '0':
            demo_1_index_search()
            demo_2_stream_warc()
            demo_3_import_data()
            demo_4_advanced_query()
            demo_5_clustering()
            demo_6_full_workflow()
        else:
            print("无效选择")

        print("\n" + "="*60)
        print("演示完成!")
        print("="*60)

    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        logger.error(f"演示失败: {e}", exc_info=True)


if __name__ == '__main__':
    main()
