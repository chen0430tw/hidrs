"""
图可视化类，生成网络拓扑的可视化图像
"""
import os
import json
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from io import BytesIO
import base64
import networkx as nx
import numpy as np
import datetime


# 检查字体文件是否存在，如果不存在则下载SimHei字体
def setup_font():
    if not os.path.exists('simhei.ttf'):
        os.system('wget -O simhei.ttf "https://github.com/StellarCN/scp_zh/raw/refs/heads/master/fonts/SimHei.ttf"')
    
    # 将下载的字体添加到Matplotlib字体管理器中
    fm.fontManager.addfont('simhei.ttf')
    # 设置默认字体为SimHei
    matplotlib.rcParams['font.sans-serif'] = ['SimHei']
    matplotlib.rcParams['axes.unicode_minus'] = False  # 正确显示负号


class GraphVisualizer:
    """图可视化类，生成网络拓扑的可视化图像"""
    
    def __init__(self, config_path="config/graph_visualizer_config.json"):
        """初始化图可视化器"""
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 配置Matplotlib
        setup_font()
        
        # 如果需要，导入UMAP
        self.use_umap = self.config['use_umap_layout']
        if self.use_umap:
            try:
                import umap
                self.umap_reducer = umap.UMAP(
                    n_neighbors=self.config['umap_n_neighbors'],
                    min_dist=self.config['umap_min_dist'],
                    n_components=2,
                    random_state=42
                )
            except ImportError:
                print("UMAP not available, falling back to default layout")
                self.use_umap = False
    
    def generate_graph_image(self, graph, title="Network Topology", figsize=(10, 8), node_color_by='cluster'):
        """
        生成网络拓扑图像
        
        参数:
        - graph: NetworkX图对象
        - title: 图标题
        - figsize: 图像尺寸
        - node_color_by: 节点着色方式（'cluster'或'fiedler'）
        
        返回:
        - 图像的Base64编码
        """
        # 创建新的图像
        plt.figure(figsize=figsize)
        
        # 如果图为空，返回空白图像
        if graph.number_of_nodes() == 0:
            plt.title("Empty Graph")
            return self._figure_to_base64()
        
        # 计算布局
        pos = self._compute_layout(graph)
        
        # 确定节点颜色
        node_colors = self._get_node_colors(graph, node_color_by)
        
        # 绘制图
        nx.draw_networkx_nodes(graph, pos, node_color=node_colors, node_size=200, alpha=0.8)
        nx.draw_networkx_edges(graph, pos, alpha=0.5)
        
        # 如果节点数量不太多，显示标签
        if graph.number_of_nodes() <= self.config['max_nodes_for_labels']:
            # 创建标签映射，限制长度
            labels = {}
            for node in graph.nodes():
                label = str(node)
                if len(label) > self.config['max_label_length']:
                    label = label[:self.config['max_label_length']] + '...'
                labels[node] = label
            nx.draw_networkx_labels(graph, pos, labels=labels, font_size=8)
        
        # 添加标题
        plt.title(title)
        plt.axis('off')
        
        # 转换为Base64
        img_base64 = self._figure_to_base64()
        plt.close()
        
        return img_base64
    
    def _compute_layout(self, graph):
        """计算图布局"""
        if self.use_umap and graph.number_of_nodes() > 2:
            try:
                # 获取邻接矩阵
                adj_matrix = nx.to_numpy_array(graph)
                
                # 使用UMAP降维
                embedding = self.umap_reducer.fit_transform(adj_matrix)
                
                # 构建位置字典
                pos = {node: (embedding[i, 0], embedding[i, 1]) for i, node in enumerate(graph.nodes())}
                return pos
            except Exception as e:
                print(f"UMAP layout failed: {str(e)}")
        
        # 如果UMAP不可用或失败，回退到spring布局
        return nx.spring_layout(graph, seed=42)
    
    def _get_node_colors(self, graph, color_by):
        """获取节点颜色"""
        if color_by == 'cluster':
            # 按聚类着色
            cluster_values = []
            for node in graph.nodes():
                cluster = graph.nodes[node].get('cluster', 0)
                cluster_values.append(cluster)
            
            return cluster_values
        
        elif color_by == 'fiedler':
            # 按Fiedler向量分量着色
            fiedler_values = []
            for node in graph.nodes():
                fiedler_component = graph.nodes[node].get('fiedler_component', 0)
                fiedler_values.append(fiedler_component)
            
            return fiedler_values
        
        # 默认使用随机颜色
        return [hash(node) % 20 for node in graph.nodes()]
    
    def _figure_to_base64(self):
        """将当前图像转换为Base64编码"""
        img_buffer = BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight')
        img_buffer.seek(0)
        img_data = base64.b64encode(img_buffer.getvalue()).decode()
        return img_data
    
    def generate_metrics_plot(self, data, x_key, y_key, title, xlabel, ylabel, figsize=(10, 6)):
        """
        生成指标变化图
        
        参数:
        - data: 数据列表，每项应包含x_key和y_key指定的字段
        - x_key: x轴数据键名
        - y_key: y轴数据键名
        - title: 图表标题
        - xlabel: x轴标签
        - ylabel: y轴标签
        - figsize: 图像尺寸
        
        返回:
        - 图像的Base64编码
        """
        plt.figure(figsize=figsize)
        
        if not data:
            plt.title("No Data Available")
            return self._figure_to_base64()
        
        # 提取数据
        x_values = [item[x_key] for item in data]
        y_values = [item[y_key] for item in data]
        
        # 绘制折线图
        plt.plot(x_values, y_values, 'b-', marker='o')
        
        # 添加标签和标题
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 如果x轴是日期时间，调整旋转
        if isinstance(x_values[0], (datetime.datetime, datetime.date)):
            plt.xticks(rotation=45)
            plt.tight_layout()
        
        # 转换为Base64
        img_base64 = self._figure_to_base64()
        plt.close()
        
        return img_base64