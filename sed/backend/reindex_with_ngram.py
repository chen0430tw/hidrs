#!/usr/bin/env python3
"""
SED索引重建脚本（保留现有数据）
使用Elasticsearch reindex API迁移到新的N-gram索引
"""
import sys
import time
from es_utils import ESClient
from conf.config import ElasticConfig
from elasticsearch.helpers import reindex

def main():
    """主函数"""
    client = ESClient()
    es = client.es

    old_index = ElasticConfig.ES_INDEX
    new_index = f"{old_index}_ngram"
    temp_alias = f"{old_index}_temp"

    print("=" * 60)
    print("SED Elasticsearch索引重建工具")
    print("=" * 60)
    print(f"旧索引: {old_index}")
    print(f"新索引: {new_index}")
    print()

    # 检查旧索引是否存在
    if not es.indices.exists(index=old_index):
        print(f"❌ 错误: 索引 {old_index} 不存在")
        print("提示: 如果这是首次运行，请直接使用新配置导入数据")
        sys.exit(1)

    # 获取文档数量
    old_count = es.count(index=old_index).get('count', 0)
    print(f"📊 旧索引文档数: {old_count:,}")

    if old_count == 0:
        print("⚠️  旧索引为空，直接删除并重建")
        es.indices.delete(index=old_index, ignore=[404])
        client.create_index_if_not_exists(old_index)
        print("✅ 新索引创建完成")
        return

    # 确认操作
    print()
    print("⚠️  警告: 此操作将重建索引，过程中可能影响查询性能")
    confirm = input("是否继续？(yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("❌ 操作已取消")
        sys.exit(0)

    print()
    print("开始重建索引...")
    print()

    # 步骤1: 创建新索引
    print("步骤 1/5: 创建新索引（使用N-gram配置）")
    if es.indices.exists(index=new_index):
        print(f"  - 删除已存在的新索引 {new_index}")
        es.indices.delete(index=new_index)

    print(f"  - 创建新索引 {new_index}")
    es.indices.create(index=new_index, body=ElasticConfig.ES_MAPPING)
    print("  ✓ 新索引创建成功")
    print()

    # 步骤2: 使用reindex API迁移数据
    print("步骤 2/5: 迁移数据（使用reindex API）")
    print("  - 这可能需要几分钟，取决于数据量...")

    start_time = time.time()

    try:
        # 使用scroll复制数据
        result = es.reindex(
            body={
                "source": {"index": old_index},
                "dest": {"index": new_index}
            },
            wait_for_completion=True,
            request_timeout=3600  # 1小时超时
        )

        elapsed = time.time() - start_time
        copied = result.get('created', 0) + result.get('updated', 0)

        print(f"  ✓ 迁移完成: {copied:,} 个文档")
        print(f"  - 耗时: {elapsed:.2f} 秒")
        print(f"  - 速度: {copied/elapsed:.0f} 文档/秒")

    except Exception as e:
        print(f"  ❌ 迁移失败: {str(e)}")
        print("  清理新索引...")
        es.indices.delete(index=new_index, ignore=[404])
        sys.exit(1)

    print()

    # 步骤3: 验证数据完整性
    print("步骤 3/5: 验证数据完整性")
    new_count = es.count(index=new_index).get('count', 0)
    print(f"  - 旧索引文档数: {old_count:,}")
    print(f"  - 新索引文档数: {new_count:,}")

    if new_count != old_count:
        print(f"  ⚠️  警告: 文档数不一致 (差异: {abs(new_count - old_count)})")
        confirm = input("  是否继续切换？(yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("  操作已取消，保留旧索引")
            es.indices.delete(index=new_index)
            sys.exit(1)
    else:
        print("  ✓ 数据完整")

    print()

    # 步骤4: 切换索引（原子操作）
    print("步骤 4/5: 切换索引（使用别名实现零停机）")

    # 创建临时别名指向新索引
    print(f"  - 创建别名 {old_index} 指向新索引")
    es.indices.update_aliases(body={
        "actions": [
            {"remove": {"index": old_index, "alias": temp_alias}},  # 移除旧别名（如果存在）
            {"add": {"index": new_index, "alias": old_index}}  # 新索引使用旧名称作为别名
        ]
    })

    print("  ✓ 别名切换完成")
    print()

    # 步骤5: 删除旧索引
    print("步骤 5/5: 清理旧索引")
    confirm = input("  是否删除旧索引以释放空间？(yes/no): ").strip().lower()
    if confirm in ['yes', 'y']:
        # 注意：此时old_index实际是别名，真正的旧索引名需要查询
        # 为了安全，我们不自动删除，让用户手动删除
        print(f"  ⚠️  请手动删除旧索引:")
        print(f"     curl -X DELETE http://localhost:9200/{old_index}_old")
        print(f"  提示: 新索引名称为 {new_index}，已通过别名 {old_index} 访问")
    else:
        print("  - 保留旧索引（可稍后手动删除）")

    print()
    print("=" * 60)
    print("✅ 索引重建完成！")
    print("=" * 60)
    print()
    print("后续步骤:")
    print(f"1. 测试查询: curl 'http://localhost:5000/api/find/email/gmail?limit=10'")
    print(f"2. 验证N-gram生效: 查询应该使用 .ngram 子字段")
    print(f"3. 确认无误后删除旧索引释放空间")
    print()
    print("注意事项:")
    print("- 当前 {old_index} 是别名，实际索引是 {new_index}")
    print("- 应用代码无需修改，继续使用 {old_index} 查询")
    print("- 如需回滚，修改别名指向旧索引即可")
    print()

if __name__ == '__main__':
    main()
