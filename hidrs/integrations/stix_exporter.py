"""
STIX 2.1导出模块
将HIDRS情报数据导出为STIX 2.1格式，供威胁情报平台使用

STIX 2.1标准：
https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html

支持的平台：
- OpenCTI
- MISP
- ThreatConnect
- Anomali ThreatStream
- IBM X-Force Exchange

使用方式：
```python
exporter = STIXExporter()

# 导出HIDRS搜索结果
stix_bundle = exporter.export_search_results(results)

# 保存为JSON文件
with open('threat_intel.json', 'w') as f:
    f.write(stix_bundle.serialize(pretty=True))

# 或导入到OpenCTI
exporter.import_to_opencti(stix_bundle, opencti_url, opencti_token)
```
"""

import json
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# STIX 2.1库
try:
    from stix2 import (
        Bundle, Indicator, ObservedData, Relationship,
        DomainName, IPv4Address, IPv6Address, URL, EmailAddress,
        Identity, TLP_WHITE, TLP_GREEN, TLP_AMBER, TLP_RED
    )
    STIX2_AVAILABLE = True
except ImportError:
    STIX2_AVAILABLE = False
    logger.warning("stix2库未安装，请运行: pip install stix2")


class STIXExporter:
    """STIX 2.1导出器"""

    def __init__(self, organization_name: str = "HIDRS", organization_identity: str = None):
        """
        初始化STIX导出器

        参数:
        - organization_name: 组织名称
        - organization_identity: 组织身份ID（可选）
        """
        if not STIX2_AVAILABLE:
            raise ImportError("需要安装stix2库: pip install stix2")

        self.organization_name = organization_name

        # 创建组织身份对象
        self.identity = Identity(
            id=organization_identity or f"identity--{uuid.uuid4()}",
            name=organization_name,
            identity_class="organization",
            description="HIDRS - Holographic Internet Discovery & Retrieval System"
        )

    def export_search_results(
        self,
        results: List[Dict],
        tlp_level: str = "white",
        confidence: int = 75
    ) -> 'Bundle':
        """
        导出HIDRS搜索结果为STIX Bundle

        参数:
        - results: HIDRS搜索结果列表
        - tlp_level: TLP级别 (white/green/amber/red)
        - confidence: 可信度 (0-100)

        返回:
        - STIX Bundle对象
        """
        stix_objects = [self.identity]

        # TLP标记
        tlp_marking = self._get_tlp_marking(tlp_level)

        for result in results:
            try:
                # 提取URL
                url = result.get('url')
                if url:
                    # 创建URL观测数据
                    url_obj = self._create_url_observable(url, result, tlp_marking)
                    if url_obj:
                        stix_objects.append(url_obj)

                    # 提取域名
                    domain = self._extract_domain(url)
                    if domain:
                        domain_obj = self._create_domain_observable(
                            domain, result, tlp_marking
                        )
                        if domain_obj:
                            stix_objects.append(domain_obj)

                # 如果有HLIG得分，创建指标
                fiedler_score = result.get('metadata', {}).get('fiedler_score')
                if fiedler_score and fiedler_score > 0.7:  # 高得分可能表示重要性
                    indicator = self._create_indicator(
                        result, confidence, tlp_marking
                    )
                    if indicator:
                        stix_objects.append(indicator)

            except Exception as e:
                logger.error(f"导出结果失败: {e}", exc_info=True)
                continue

        # 创建Bundle
        bundle = Bundle(objects=stix_objects)
        return bundle

    def export_network_topology(
        self,
        topology_data: Dict,
        tlp_level: str = "green"
    ) -> 'Bundle':
        """
        导出HIDRS网络拓扑为STIX Bundle

        参数:
        - topology_data: 拓扑数据
        - tlp_level: TLP级别

        返回:
        - STIX Bundle对象
        """
        stix_objects = [self.identity]
        tlp_marking = self._get_tlp_marking(tlp_level)

        # 创建网络拓扑观测数据
        observed_data = ObservedData(
            first_observed=datetime.utcnow(),
            last_observed=datetime.utcnow(),
            number_observed=1,
            objects={
                "0": {
                    "type": "x-hidrs-topology",  # 自定义对象类型
                    "fiedler_value": topology_data.get('fiedler_value', 0),
                    "node_count": topology_data.get('node_count', 0),
                    "edge_count": topology_data.get('edge_count', 0),
                    "clustering_coefficient": topology_data.get('clustering_coefficient', 0)
                }
            },
            object_marking_refs=[tlp_marking],
            created_by_ref=self.identity.id
        )

        stix_objects.append(observed_data)

        return Bundle(objects=stix_objects)

    def export_commoncrawl_data(
        self,
        cc_results: List[Dict],
        tlp_level: str = "white"
    ) -> 'Bundle':
        """
        导出Common Crawl数据为STIX Bundle

        参数:
        - cc_results: Common Crawl搜索结果
        - tlp_level: TLP级别

        返回:
        - STIX Bundle对象
        """
        stix_objects = [self.identity]
        tlp_marking = self._get_tlp_marking(tlp_level)

        for result in cc_results:
            try:
                url = result.get('url')
                if not url:
                    continue

                # 创建观测数据
                observed_data = ObservedData(
                    first_observed=self._parse_timestamp(result.get('timestamp')),
                    last_observed=self._parse_timestamp(result.get('timestamp')),
                    number_observed=1,
                    objects={
                        "0": URL(value=url),
                        "1": {
                            "type": "x-commoncrawl-record",
                            "crawl_id": result.get('crawl_id', ''),
                            "warc_file": result.get('warc_file', ''),
                            "title": result.get('title', '')
                        }
                    },
                    object_marking_refs=[tlp_marking],
                    created_by_ref=self.identity.id
                )

                stix_objects.append(observed_data)

            except Exception as e:
                logger.error(f"导出Common Crawl数据失败: {e}")
                continue

        return Bundle(objects=stix_objects)

    def _create_url_observable(
        self,
        url: str,
        result: Dict,
        tlp_marking
    ) -> Optional['ObservedData']:
        """创建URL观测数据"""
        try:
            observed_data = ObservedData(
                first_observed=datetime.utcnow(),
                last_observed=datetime.utcnow(),
                number_observed=1,
                objects={
                    "0": URL(value=url)
                },
                object_marking_refs=[tlp_marking],
                created_by_ref=self.identity.id
            )
            return observed_data
        except Exception as e:
            logger.error(f"创建URL观测数据失败: {e}")
            return None

    def _create_domain_observable(
        self,
        domain: str,
        result: Dict,
        tlp_marking
    ) -> Optional['ObservedData']:
        """创建域名观测数据"""
        try:
            observed_data = ObservedData(
                first_observed=datetime.utcnow(),
                last_observed=datetime.utcnow(),
                number_observed=1,
                objects={
                    "0": DomainName(value=domain)
                },
                object_marking_refs=[tlp_marking],
                created_by_ref=self.identity.id
            )
            return observed_data
        except Exception as e:
            logger.error(f"创建域名观测数据失败: {e}")
            return None

    def _create_indicator(
        self,
        result: Dict,
        confidence: int,
        tlp_marking
    ) -> Optional['Indicator']:
        """创建STIX指标"""
        try:
            url = result.get('url')
            if not url:
                return None

            # 构建指标模式
            domain = self._extract_domain(url)
            pattern = f"[url:value = '{url}']"

            indicator = Indicator(
                name=result.get('title', 'HIDRS发现的URL'),
                description=f"HIDRS搜索发现 | Fiedler得分: {result.get('metadata', {}).get('fiedler_score', 'N/A')}",
                pattern=pattern,
                pattern_type="stix",
                valid_from=datetime.utcnow(),
                confidence=confidence,
                labels=["osint", "hidrs", "hlig"],
                object_marking_refs=[tlp_marking],
                created_by_ref=self.identity.id
            )

            return indicator

        except Exception as e:
            logger.error(f"创建指标失败: {e}")
            return None

    def _get_tlp_marking(self, level: str):
        """获取TLP标记"""
        tlp_map = {
            'white': TLP_WHITE,
            'green': TLP_GREEN,
            'amber': TLP_AMBER,
            'red': TLP_RED
        }
        return tlp_map.get(level.lower(), TLP_WHITE)

    def _extract_domain(self, url: str) -> Optional[str]:
        """从URL提取域名"""
        try:
            parsed = urlparse(url)
            return parsed.netloc if parsed.netloc else None
        except:
            return None

    def _parse_timestamp(self, timestamp_str: Optional[str]) -> datetime:
        """解析时间戳"""
        if not timestamp_str:
            return datetime.utcnow()

        try:
            # 尝试多种格式
            for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                try:
                    return datetime.strptime(timestamp_str, fmt)
                except:
                    continue
            return datetime.utcnow()
        except:
            return datetime.utcnow()

    def save_to_file(self, bundle: 'Bundle', filepath: str, pretty: bool = True):
        """
        保存STIX Bundle到文件

        参数:
        - bundle: STIX Bundle对象
        - filepath: 文件路径
        - pretty: 是否格式化输出
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(bundle.serialize(pretty=pretty, ensure_ascii=False))
            logger.info(f"STIX Bundle已保存到: {filepath}")
        except Exception as e:
            logger.error(f"保存文件失败: {e}")
            raise

    def import_to_opencti(
        self,
        bundle: 'Bundle',
        opencti_url: str,
        opencti_token: str
    ) -> bool:
        """
        导入STIX Bundle到OpenCTI

        参数:
        - bundle: STIX Bundle对象
        - opencti_url: OpenCTI服务器URL
        - opencti_token: OpenCTI API令牌

        返回:
        - 是否成功
        """
        try:
            from pycti import OpenCTIApiClient

            # 初始化OpenCTI客户端
            opencti_client = OpenCTIApiClient(
                url=opencti_url,
                token=opencti_token
            )

            # 导入Bundle
            opencti_client.stix2.import_bundle_from_json_file(
                bundle.serialize()
            )

            logger.info("成功导入到OpenCTI")
            return True

        except ImportError:
            logger.error("pycti库未安装，请运行: pip install pycti")
            return False
        except Exception as e:
            logger.error(f"导入到OpenCTI失败: {e}")
            return False


# 示例代码
if __name__ == '__main__':
    print("HIDRS STIX 2.1导出模块")
    print("=" * 50)

    if not STIX2_AVAILABLE:
        print("错误: 需要安装stix2库")
        print("运行: pip install stix2")
        exit(1)

    # 创建导出器
    exporter = STIXExporter(organization_name="HIDRS Demo")

    # 模拟搜索结果
    mock_results = [
        {
            'url': 'https://example.com/article',
            'title': 'Example Article',
            'metadata': {
                'fiedler_score': 0.85
            }
        },
        {
            'url': 'https://test.org/page',
            'title': 'Test Page',
            'metadata': {
                'fiedler_score': 0.45
            }
        }
    ]

    # 导出为STIX Bundle
    bundle = exporter.export_search_results(mock_results, tlp_level="green")

    # 打印JSON
    print("\nSTIX 2.1 Bundle:")
    print(bundle.serialize(pretty=True))

    # 保存到文件
    exporter.save_to_file(bundle, 'hidrs_threat_intel.json')
    print("\n已保存到: hidrs_threat_intel.json")
