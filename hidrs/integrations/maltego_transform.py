"""
Maltego Transform整合
将HIDRS搜索结果转换为Maltego实体和关系图谱

Maltego Transform文档：
https://docs.maltego.com/support/solutions/articles/15000017605-writing-local-transforms-in-python

使用方式：
1. 在Maltego中配置Local Transform
2. 设置命令为: python maltego_transform.py
3. 输入实体类型：Domain/Email/Person/PhoneNumber
"""

import sys
import json
import logging
from typing import Dict, List, Any
from xml.etree.ElementTree import Element, SubElement, tostring

logger = logging.getLogger(__name__)


class MaltegoEntity:
    """Maltego实体基类"""

    # Maltego标准实体类型
    ENTITY_TYPES = {
        'domain': 'maltego.Domain',
        'email': 'maltego.EmailAddress',
        'person': 'maltego.Person',
        'phone': 'maltego.PhoneNumber',
        'url': 'maltego.URL',
        'ipv4': 'maltego.IPv4Address',
        'document': 'maltego.Document',
        'location': 'maltego.Location',
        'organization': 'maltego.Organization',
        'hashtag': 'maltego.Hashtag',
        'alias': 'maltego.Alias'
    }

    def __init__(self, entity_type: str, value: str):
        """
        初始化Maltego实体

        参数:
        - entity_type: 实体类型（domain/email/person等）
        - value: 实体值
        """
        self.entity_type = self.ENTITY_TYPES.get(entity_type, 'maltego.Phrase')
        self.value = value
        self.properties = {}
        self.weight = 100
        self.icon_url = None

    def add_property(self, name: str, value: Any, display_name: str = None):
        """添加实体属性"""
        self.properties[name] = {
            'value': str(value),
            'display_name': display_name or name
        }

    def to_xml(self) -> Element:
        """转换为Maltego XML格式"""
        entity = Element('Entity', Type=self.entity_type)

        # 实体值
        value_elem = SubElement(entity, 'Value')
        value_elem.text = str(self.value)

        # 权重
        weight_elem = SubElement(entity, 'Weight')
        weight_elem.text = str(self.weight)

        # 属性
        if self.properties:
            additional_fields = SubElement(entity, 'AdditionalFields')
            for name, prop in self.properties.items():
                field = SubElement(additional_fields, 'Field',
                                 Name=name,
                                 DisplayName=prop['display_name'])
                field.text = prop['value']

        # 图标
        if self.icon_url:
            icon_elem = SubElement(entity, 'IconURL')
            icon_elem.text = self.icon_url

        return entity


class MaltegoTransform:
    """Maltego Transform主类"""

    def __init__(self):
        """初始化Transform"""
        self.entities = []
        self.ui_messages = []

    def add_entity(self, entity: MaltegoEntity):
        """添加实体到返回结果"""
        self.entities.append(entity)

    def add_ui_message(self, message: str, message_type: str = 'Inform'):
        """
        添加UI消息

        参数:
        - message: 消息内容
        - message_type: 消息类型 (Inform/PartialError/FatalError/Debug)
        """
        self.ui_messages.append({
            'message': message,
            'type': message_type
        })

    def return_output(self):
        """返回Maltego XML输出"""
        # 构建MaltegoMessage XML
        maltego_msg = Element('MaltegoMessage')
        maltego_transform = SubElement(maltego_msg, 'MaltegoTransformResponseMessage')

        # 添加实体
        entities_elem = SubElement(maltego_transform, 'Entities')
        for entity in self.entities:
            entities_elem.append(entity.to_xml())

        # 添加UI消息
        if self.ui_messages:
            ui_messages_elem = SubElement(maltego_transform, 'UIMessages')
            for msg in self.ui_messages:
                ui_msg = SubElement(ui_messages_elem, 'UIMessage', MessageType=msg['type'])
                ui_msg.text = msg['message']

        # 输出XML
        xml_str = tostring(maltego_msg, encoding='utf-8', method='xml')
        print(xml_str.decode('utf-8'))

    def transform_hidrs_search(self, query: str, entity_type: str = 'phrase'):
        """
        HIDRS搜索Transform

        将HIDRS搜索结果转换为Maltego实体
        """
        try:
            from hidrs.realtime_search.search_engine import RealtimeSearchEngine

            # 初始化搜索引擎
            search_engine = RealtimeSearchEngine(
                elasticsearch_host='localhost:9200',
                enable_hlig=True
            )

            # 执行搜索
            results = search_engine.search(
                query_text=query,
                limit=50,
                use_cache=False
            )

            if not results or 'results' not in results:
                self.add_ui_message("未找到搜索结果", "PartialError")
                return

            # 转换为Maltego实体
            for result in results['results']:
                url = result.get('url', '')
                title = result.get('title', '')
                source = result.get('source', 'unknown')
                fiedler_score = result.get('metadata', {}).get('fiedler_score', 0)

                if url:
                    # 创建URL实体
                    entity = MaltegoEntity('url', url)
                    entity.add_property('title', title, 'Title')
                    entity.add_property('source', source, 'Source')
                    entity.add_property('fiedler_score',
                                      f'{fiedler_score:.4f}',
                                      'HLIG Fiedler Score')
                    entity.weight = int(fiedler_score * 100) if fiedler_score else 50

                    self.add_entity(entity)

                    # 提取域名
                    if '://' in url:
                        domain = url.split('://')[1].split('/')[0]
                        domain_entity = MaltegoEntity('domain', domain)
                        domain_entity.add_property('source', source, 'Source')
                        self.add_entity(domain_entity)

            self.add_ui_message(f"找到 {len(results['results'])} 个结果", "Inform")

        except Exception as e:
            logger.error(f"Transform失败: {e}", exc_info=True)
            self.add_ui_message(f"Transform失败: {str(e)}", "FatalError")

    def transform_commoncrawl_search(self, query: str):
        """
        Common Crawl搜索Transform

        从Common Crawl数据库检索历史网页
        """
        try:
            from hidrs.commoncrawl import CommonCrawlQueryEngine

            # 初始化查询引擎
            query_engine = CommonCrawlQueryEngine(
                mongodb_uri='mongodb://localhost:27017',
                db_name='hidrs'
            )

            # 执行搜索
            keywords = [k.strip() for k in query.split(',')]
            results = query_engine.advanced_search(
                keywords=keywords,
                limit=30
            )

            if not results:
                self.add_ui_message("Common Crawl未找到结果", "PartialError")
                return

            # 转换为Maltego实体
            for result in results:
                url = result.get('url', '')
                title = result.get('title', '')
                timestamp = result.get('timestamp', '')
                crawl_id = result.get('crawl_id', '')

                if url:
                    entity = MaltegoEntity('url', url)
                    entity.add_property('title', title, 'Title')
                    entity.add_property('crawl_time', timestamp, 'Crawl Time')
                    entity.add_property('crawl_id', crawl_id, 'Crawl ID')
                    entity.add_property('source', 'Common Crawl', 'Source')

                    if 'fiedler_score' in result:
                        entity.add_property('fiedler_score',
                                          f"{result['fiedler_score']:.4f}",
                                          'HLIG Score')
                        entity.weight = int(result['fiedler_score'] * 100)

                    self.add_entity(entity)

            self.add_ui_message(f"从Common Crawl找到 {len(results)} 个历史记录", "Inform")

        except Exception as e:
            logger.error(f"Common Crawl Transform失败: {e}", exc_info=True)
            self.add_ui_message(f"Transform失败: {str(e)}", "FatalError")

    def transform_network_topology(self, domain: str):
        """
        网络拓扑Transform

        分析域名在HIDRS网络拓扑中的位置
        """
        try:
            from hidrs.network_topology.topology_manager import TopologyManager

            # 初始化拓扑管理器
            topology_mgr = TopologyManager()

            # 获取拓扑信息
            topology_info = topology_mgr.get_topology_info()

            # 查找与该域名相关的节点
            # （这里简化处理，实际需要根据你的拓扑数据结构调整）

            # 创建拓扑中心节点
            center_entity = MaltegoEntity('domain', domain)
            center_entity.add_property('fiedler_value',
                                      str(topology_info.get('fiedler_value', 0)),
                                      'Fiedler Value')
            center_entity.add_property('node_count',
                                      str(topology_info.get('node_count', 0)),
                                      'Total Nodes')
            self.add_entity(center_entity)

            self.add_ui_message("拓扑分析完成", "Inform")

        except Exception as e:
            logger.error(f"拓扑Transform失败: {e}", exc_info=True)
            self.add_ui_message(f"Transform失败: {str(e)}", "FatalError")


def main():
    """
    Maltego Transform主入口

    从命令行接收参数并执行Transform
    """
    # Maltego传递参数格式:
    # sys.argv[1] = 实体值
    # sys.argv[2] = 实体类型
    # sys.argv[3+] = Transform参数

    if len(sys.argv) < 2:
        print("用法: python maltego_transform.py <实体值> [transform类型]")
        sys.exit(1)

    entity_value = sys.argv[1]
    transform_type = sys.argv[2] if len(sys.argv) > 2 else 'search'

    # 创建Transform
    transform = MaltegoTransform()

    # 根据类型执行不同的Transform
    if transform_type == 'search':
        transform.transform_hidrs_search(entity_value)
    elif transform_type == 'commoncrawl':
        transform.transform_commoncrawl_search(entity_value)
    elif transform_type == 'topology':
        transform.transform_network_topology(entity_value)
    else:
        transform.add_ui_message(f"未知的Transform类型: {transform_type}", "FatalError")

    # 返回结果
    transform.return_output()


if __name__ == '__main__':
    main()
