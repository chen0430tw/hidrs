#!/usr/bin/env python3
"""
联邦搜索系统演示 - Federated Search Demo

展示如何使用HLIG理论的联邦搜索系统：
1. HIDRS Core作为主搜索路径
2. Google/百度/Archive作为降级层
3. 所有结果经过HLIG重排序
4. 监控系统身份纯度（忒修斯之船判断）

使用方法:
    python examples/federated_search_demo.py

环境变量:
    GOOGLE_SEARCH_API_KEY - Google Custom Search API密钥
    GOOGLE_SEARCH_ENGINE_ID - Google搜索引擎ID
"""
import os
import sys
import json
import logging
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hidrs.federated_search import (
    HIDRSAdapter,
    GoogleSearchAdapter,
    BaiduSearchAdapter,
    ArchiveSearchAdapter,
    FederatedSearchEngine
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def print_separator(title=""):
    """打印分隔符"""
    width = 80
    if title:
        padding = (width - len(title) - 2) // 2
        print("=" * padding + f" {title} " + "=" * padding)
    else:
        print("=" * width)


def print_result(result: dict, index: int):
    """打印单个搜索结果"""
    print(f"\n[{index + 1}] {result['title']}")
    print(f"    URL: {result['url']}")
    print(f"    来源: {result['source']}")
    print(f"    得分: {result.get('final_score', result.get('score', 0)):.4f}")

    # 显示HLIG分析信息
    metadata = result.get('metadata', {})
    if metadata.get('hlig_reranked'):
        fiedler_score = metadata.get('fiedler_score', 0)
        fiedler_value = metadata.get('fiedler_value', 0)
        print(f"    ✅ HLIG: Fiedler得分={fiedler_score:.4f}, λ₂={fiedler_value:.6f}")

    snippet = result.get('snippet', '')
    if snippet:
        # 限制摘要长度
        if len(snippet) > 150:
            snippet = snippet[:150] + "..."
        print(f"    摘要: {snippet}")


def demo_basic_search(engine: FederatedSearchEngine):
    """演示基础搜索"""
    print_separator("基础搜索演示")

    query = "拉普拉斯矩阵 谱分析"
    print(f"\n搜索查询: {query}")

    result = engine.search(query, limit=5)

    print(f"\n结果来源: {result['source']}")
    print(f"使用的适配器: {result['adapter_used']}")
    print(f"是否触发降级: {'是' if result['fallback_triggered'] else '否'}")
    print(f"是否应用HLIG: {'是' if result['hlig_applied'] else '否'}")
    print(f"总结果数: {len(result['results'])}")

    print("\n搜索结果:")
    for idx, item in enumerate(result['results']):
        print_result(item, idx)

    return result


def demo_fallback_scenario(engine: FederatedSearchEngine):
    """演示降级场景"""
    print_separator("降级场景演示")

    print("\n场景: HIDRS Core不可用，系统自动降级到外部搜索源")
    print("即使使用外部源，结果也会经过HLIG重排序以保持HIDRS身份\n")

    # 模拟核心不可用
    core_adapter = engine.core_adapter
    if core_adapter:
        original_state = core_adapter._available
        core_adapter._available = False
        print(f"[模拟] 将 {core_adapter.name} 设置为不可用")

    query = "holographic laplacian internet graph"
    print(f"\n搜索查询: {query}")

    result = engine.search(query, limit=5)

    print(f"\n结果来源: {result['source']}")
    print(f"使用的适配器: {result['adapter_used']}")
    print(f"是否触发降级: {'是' if result['fallback_triggered'] else '否'}")
    print(f"是否应用HLIG: {'是' if result['hlig_applied'] else '否'}")

    # 关键判断：即使降级，HLIG也应该被应用
    if result['fallback_triggered'] and result['hlig_applied']:
        print("\n✅ 忒修斯之船判断: 系统仍是HIDRS（外部结果经过HLIG重排序）")
    elif result['fallback_triggered'] and not result['hlig_applied']:
        print("\n❌ 忒修斯之船判断: 系统变成搜索聚合器（未应用HLIG）")

    print("\n搜索结果:")
    for idx, item in enumerate(result['results']):
        print_result(item, idx)

    # 恢复核心状态
    if core_adapter:
        core_adapter._available = original_state
        print(f"\n[恢复] 将 {core_adapter.name} 恢复为可用")

    return result


def demo_identity_monitoring(engine: FederatedSearchEngine):
    """演示身份监控"""
    print_separator("系统身份监控")

    status = engine.get_system_status()

    print("\n系统健康状态:")
    health = status['health']
    print(f"  健康状态: {health['status']}")
    print(f"  可用适配器: {health['available_adapters']}/{health['total_adapters']}")
    print(f"  核心适配器: {health['core_adapter']}")

    print("\n降级链状态:")
    for adapter_status in health.get('adapter_status', []):
        status_icon = "✅" if adapter_status['available'] else "❌"
        print(f"  {status_icon} [{adapter_status['priority']}] {adapter_status['name']} ({adapter_status['type']})")

    print("\n统计信息:")
    stats = health.get('stats', {})
    print(f"  总搜索次数: {stats.get('total_searches', 0)}")
    print(f"  核心成功次数: {stats.get('core_successes', 0)}")
    print(f"  降级触发次数: {stats.get('fallback_triggers', 0)}")
    print(f"  核心成功率: {stats.get('core_success_rate', 0):.2%}")
    print(f"  降级率: {stats.get('fallback_rate', 0):.2%}")

    print("\n忒修斯之船判断:")
    identity = status['identity_analysis']
    print(f"  身份纯度: {identity['identity_purity']:.1f}/100")
    print(f"  是否仍是HIDRS: {'是' if identity['still_hidrs'] else '否'}")
    print(f"  判断结果: {identity['judgment']}")

    print("\n配置信息:")
    config = status['configuration']
    print(f"  降级功能: {'启用' if config['fallback_enabled'] else '禁用'}")
    print(f"  强制HLIG: {'是' if config['always_use_hlig'] else '否'}")
    print(f"  核心适配器: {config['core_adapter']}")


def demo_comparison(engine: FederatedSearchEngine):
    """演示不同适配器对比"""
    print_separator("适配器对比演示")

    query = "artificial intelligence"
    print(f"\n搜索查询: {query}\n")

    # 测试每个适配器
    adapters = engine.fallback_handler.adapters

    for adapter in adapters:
        if not adapter.is_available():
            print(f"\n[跳过] {adapter.name} - 不可用")
            continue

        print(f"\n[测试] {adapter.name} (优先级: {adapter.priority})")
        try:
            results = adapter.search(query, limit=3)
            print(f"  返回结果数: {len(results)}")

            if results:
                print(f"  第一个结果:")
                print(f"    标题: {results[0]['title'][:60]}...")
                print(f"    得分: {results[0].get('score', 0):.4f}")
        except Exception as e:
            print(f"  ❌ 错误: {e}")


def main():
    """主函数"""
    print_separator("HIDRS 联邦搜索系统演示")
    print("\n这是一个基于HLIG理论的联邦搜索系统")
    print("核心特性:")
    print("  1. HIDRS Core作为主搜索路径（使用Fiedler向量重排序）")
    print("  2. Google/百度/Archive作为降级层")
    print("  3. 所有结果经过HLIG谱分析重排序")
    print("  4. 实时监控系统身份纯度（忒修斯之船判断）")

    # 检查环境变量
    print("\n环境检查:")
    google_api_key = os.getenv('GOOGLE_SEARCH_API_KEY')
    google_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

    if google_api_key and google_engine_id:
        print("  ✅ Google API配置完整")
    else:
        print("  ⚠️ Google API未配置（将跳过Google搜索）")
        print("     设置环境变量: GOOGLE_SEARCH_API_KEY, GOOGLE_SEARCH_ENGINE_ID")

    # 初始化适配器
    print("\n初始化适配器...")

    # HIDRS Core (Priority 1)
    hidrs_adapter = HIDRSAdapter(
        elasticsearch_host='localhost',
        elasticsearch_port=9200,
        index_name='hidrs_documents'
    )

    # 外部适配器 (Priority 2-4)
    google_adapter = GoogleSearchAdapter(
        api_key=google_api_key,
        search_engine_id=google_engine_id
    )

    baidu_adapter = BaiduSearchAdapter(use_api=False)
    archive_adapter = ArchiveSearchAdapter()

    adapters = [
        hidrs_adapter,      # Priority 1 - Core
        google_adapter,     # Priority 2 - Fallback
        baidu_adapter,      # Priority 3 - Fallback
        archive_adapter     # Priority 4 - Fallback
    ]

    # 创建联邦搜索引擎
    engine = FederatedSearchEngine(
        adapters=adapters,
        min_results_threshold=3,
        enable_fallback=True,
        always_use_hlig=True  # 关键配置：保持HIDRS身份
    )

    print(f"✅ 联邦搜索引擎初始化完成")
    print(f"   核心适配器: {engine.core_adapter.name if engine.core_adapter else '无'}")
    print(f"   降级适配器: {len([a for a in adapters if not a.is_core()])}个")

    # 运行演示
    try:
        input("\n按Enter键开始演示...")

        # 1. 基础搜索
        demo_basic_search(engine)
        input("\n按Enter键继续...")

        # 2. 降级场景
        demo_fallback_scenario(engine)
        input("\n按Enter键继续...")

        # 3. 身份监控
        demo_identity_monitoring(engine)
        input("\n按Enter键继续...")

        # 4. 适配器对比
        demo_comparison(engine)

        print_separator("演示完成")
        print("\n总结:")
        print("  ✅ HIDRS联邦搜索系统展示了如何在保持核心身份的同时增强鲁棒性")
        print("  ✅ HLIG理论（Fiedler向量）始终应用于所有结果")
        print("  ✅ 忒修斯之船判断标准：identity_purity >= 50 = 仍是HIDRS")
        print("  ✅ 系统不是搜索聚合器，而是HLIG驱动的智能搜索引擎")

    except KeyboardInterrupt:
        print("\n\n演示被用户中断")
    except Exception as e:
        logger.error(f"演示过程中出错: {e}", exc_info=True)


if __name__ == "__main__":
    main()
