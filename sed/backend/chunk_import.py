"""
银狼数据安全平台 - 分块导入工具
支持100MB+大文件的分块处理和导入
"""
import os
import sys
import json
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ChunkImporter:
    """分块导入器"""
    
    def __init__(self, es_client, chunk_size_mb=100, batch_size=5000):
        self.es = es_client
        self.chunk_size = chunk_size_mb * 1024 * 1024  # 转换为字节
        self.batch_size = batch_size
        self.stats = {
            'total_lines': 0,
            'success': 0,
            'error': 0,
            'chunks_processed': 0,
            'start_time': None,
            'end_time': None
        }
    
    def import_file(self, filepath, parse_func, index_name='socialdb',
                    template=None, custom_fields=None, callback=None):
        """
        分块导入文件
        
        Args:
            filepath: 文件路径
            parse_func: 行解析函数 (line) -> dict
            index_name: ES索引名
            template: 格式模板（可选）
            custom_fields: 自定义固定字段（可选）
            callback: 进度回调函数 (stats) -> None
        """
        self.stats['start_time'] = datetime.now().isoformat()
        file_size = os.path.getsize(filepath)
        total_chunks = max(1, file_size // self.chunk_size + 1)
        
        logger.info(f"开始导入文件: {filepath}")
        logger.info(f"文件大小: {file_size / (1024*1024):.1f} MB, 预计分块: {total_chunks}")
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                chunk_num = 0
                batch = []
                bytes_read = 0
                
                for line_num, line in enumerate(f, 1):
                    bytes_read += len(line.encode('utf-8', errors='ignore'))
                    line = line.strip()
                    
                    if not line:
                        continue
                    
                    self.stats['total_lines'] += 1
                    
                    try:
                        # 解析行
                        record = parse_func(line)
                        
                        if record:
                            # 添加自定义字段
                            if custom_fields:
                                record.update(custom_fields)
                            
                            # 添加元数据
                            record['_import_time'] = datetime.now().isoformat()
                            record['_source_file'] = os.path.basename(filepath)
                            record['_line_number'] = line_num
                            
                            batch.append(record)
                            
                            # 批次满了就写入
                            if len(batch) >= self.batch_size:
                                success, errors = self._bulk_index(batch, index_name)
                                self.stats['success'] += success
                                self.stats['error'] += errors
                                batch = []
                    
                    except Exception as e:
                        self.stats['error'] += 1
                        if self.stats['error'] <= 10:
                            logger.warning(f"行 {line_num} 解析失败: {e}")
                    
                    # 检查是否到了新的分块边界
                    if bytes_read >= (chunk_num + 1) * self.chunk_size:
                        chunk_num += 1
                        self.stats['chunks_processed'] = chunk_num
                        logger.info(f"已处理分块 {chunk_num}/{total_chunks}, "
                                   f"成功: {self.stats['success']}, 失败: {self.stats['error']}")
                        
                        if callback:
                            callback(self.stats.copy())
                
                # 处理最后一批
                if batch:
                    success, errors = self._bulk_index(batch, index_name)
                    self.stats['success'] += success
                    self.stats['error'] += errors
                
                self.stats['chunks_processed'] = chunk_num + 1
        
        except Exception as e:
            logger.error(f"文件导入失败: {e}")
            raise
        finally:
            self.stats['end_time'] = datetime.now().isoformat()
        
        logger.info(f"导入完成 - 成功: {self.stats['success']}, "
                    f"失败: {self.stats['error']}, "
                    f"总行数: {self.stats['total_lines']}")
        
        return self.stats
    
    def _bulk_index(self, records, index_name):
        """批量索引"""
        if not records:
            return 0, 0
        
        try:
            actions = []
            for record in records:
                actions.append({'index': {'_index': index_name}})
                actions.append(record)
            
            body = '\n'.join(json.dumps(a, ensure_ascii=False) for a in actions) + '\n'
            
            response = self.es.bulk(body=body, index=index_name, refresh=False)
            
            success = 0
            errors = 0
            if response.get('errors'):
                for item in response.get('items', []):
                    if 'error' in item.get('index', {}):
                        errors += 1
                    else:
                        success += 1
            else:
                success = len(records)
            
            return success, errors
        
        except Exception as e:
            logger.error(f"批量索引失败: {e}")
            return 0, len(records)


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='银狼平台 - 分块数据导入工具')
    parser.add_argument('file', help='要导入的文件路径')
    parser.add_argument('--index', default='socialdb', help='ES索引名')
    parser.add_argument('--chunk-size', type=int, default=100, help='分块大小(MB)')
    parser.add_argument('--batch-size', type=int, default=5000, help='每批次记录数')
    parser.add_argument('--split', default='----', help='字段分隔符')
    parser.add_argument('--fields', default='email,password', help='字段列表,逗号分隔')
    parser.add_argument('--source', default='', help='数据来源标记')
    parser.add_argument('--es-host', default='localhost', help='ES主机')
    parser.add_argument('--es-port', type=int, default=9200, help='ES端口')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"文件不存在: {args.file}")
        sys.exit(1)
    
    from elasticsearch import Elasticsearch
    es = Elasticsearch([{'host': args.es_host, 'port': args.es_port}])
    
    fields = args.fields.split(',')
    split_char = args.split
    custom_fields = {}
    if args.source:
        custom_fields['source'] = args.source
    
    def parse_line(line):
        parts = line.split(split_char)
        record = {}
        for i, field in enumerate(fields):
            if i < len(parts):
                record[field] = parts[i].strip()
        return record if record else None
    
    importer = ChunkImporter(es, chunk_size_mb=args.chunk_size, batch_size=args.batch_size)
    
    def progress_callback(stats):
        print(f"进度: 分块 {stats['chunks_processed']}, "
              f"成功 {stats['success']}, 失败 {stats['error']}, "
              f"总行数 {stats['total_lines']}")
    
    stats = importer.import_file(
        args.file,
        parse_line,
        index_name=args.index,
        custom_fields=custom_fields,
        callback=progress_callback
    )
    
    print(f"\n===== 导入完成 =====")
    print(f"总行数: {stats['total_lines']}")
    print(f"成功: {stats['success']}")
    print(f"失败: {stats['error']}")
    print(f"分块数: {stats['chunks_processed']}")


if __name__ == '__main__':
    main()
