"""
全息映射类，实现局部拉普拉斯矩阵到全局全息表示的映射
"""
import numpy as np


class HolographicMapper:
    """全息映射类，实现局部拉普拉斯矩阵到全局全息表示的映射"""
    
    def __init__(self, config_path=None):
        """
        初始化全息映射器
        
        参数:
        - config_path: 配置文件路径（可选）
        """
        self.output_dim = 256  # 默认输出维度
        self.info_preserve_ratio = 0.9  # 信息保留比率
        self.local_info_weight = 0.7  # 局部信息权重
        self.scale_decay = 2.0  # 尺度衰减因子

        # 如果提供了配置文件，读取配置
        if config_path:
            self._load_config(config_path)
    
    def _load_config(self, config_path):
        """从配置文件加载参数"""
        import json
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            self.output_dim = config.get('output_dimension', 256)
            self.info_preserve_ratio = config.get('information_preserve_ratio', 0.9)
            self.local_info_weight = config.get('local_information_weight', 0.7)
            self.scale_decay = config.get('scale_decay_factor', 2.0)
        except Exception as e:
            print(f"Error loading mapper config: {str(e)}")
    
    def map_local_to_global(self, local_laplacian, global_fiedler=None):
        """
        将局部拉普拉斯矩阵映射到全局全息表示
        
        参数:
        - local_laplacian: 局部拉普拉斯矩阵
        - global_fiedler: 全局Fiedler向量（可选）
        
        返回:
        - 全息表示向量
        """
        # 将输入转换为numpy数组
        if not isinstance(local_laplacian, np.ndarray):
            local_laplacian = np.array(local_laplacian)
        
        # 对局部拉普拉斯矩阵进行特征分解
        eigenvalues, eigenvectors = np.linalg.eigh(local_laplacian)
        
        # 根据特征值大小排序
        idx = eigenvalues.argsort()
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]
        
        # 提取局部Fiedler向量（第二小特征值对应的特征向量）
        local_fiedler = eigenvectors[:, 1] if eigenvectors.shape[1] > 1 else eigenvectors[:, 0]
        
        # 计算全息表示向量的基础部分
        holographic_base = self._compute_holographic_base(eigenvalues, eigenvectors)
        
        # 如果提供了全局Fiedler向量，融合全局和局部信息
        if global_fiedler is not None:
            global_component = self._compute_global_component(local_fiedler, global_fiedler)
            
            # 加权融合局部和全局信息
            w_local = self.local_info_weight
            w_global = 1.0 - w_local
            holographic_rep = w_local * holographic_base + w_global * global_component
        else:
            holographic_rep = holographic_base
        
        # 确保输出维度正确
        if len(holographic_rep) > self.output_dim:
            holographic_rep = holographic_rep[:self.output_dim]
        elif len(holographic_rep) < self.output_dim:
            # 如果维度不够，填充零
            padding = np.zeros(self.output_dim - len(holographic_rep))
            holographic_rep = np.concatenate([holographic_rep, padding])
        
        return holographic_rep
    
    def _compute_holographic_base(self, eigenvalues, eigenvectors):
        """计算全息表示向量的基础部分"""
        # 选择保留信息量
        total_info = np.sum(np.abs(eigenvalues))
        cum_info = np.cumsum(np.abs(eigenvalues))
        k = np.searchsorted(cum_info, self.info_preserve_ratio * total_info) + 1
        
        # 提取前k个特征值和特征向量
        k = min(k, len(eigenvalues))
        selected_values = eigenvalues[:k]
        selected_vectors = eigenvectors[:, :k]
        
        # 构建基础全息表示
        features = []
        for i in range(k):
            # 权重衰减，使得较小的特征值对应的特征向量权重更大
            weight = 1.0 / (selected_values[i] + 1e-10)
            weighted_vector = weight * selected_vectors[:, i]
            features.append(weighted_vector)
        
        # 连接特征
        holographic_base = np.concatenate(features)
        
        # 标准化
        norm = np.linalg.norm(holographic_base)
        if norm > 0:
            holographic_base = holographic_base / norm
        
        return holographic_base
    
    def _compute_global_component(self, local_fiedler, global_fiedler):
        """
        计算全局信息组件

        将局部Fiedler向量投影到全局Fiedler空间，生成与output_dim一致的
        全局表示向量。实现Φ_hol理论中局部→全局信息编码：
        G = α · (u₂_local · u₂_global) · Ψ(u₂_global)
        其中Ψ将全局Fiedler向量扩展到目标维度空间。
        """
        # 对齐维度：取两个向量的最小长度进行投影
        min_len = min(len(local_fiedler), len(global_fiedler))
        local_trunc = local_fiedler[:min_len]
        global_trunc = global_fiedler[:min_len]

        # 计算投影系数（局部结构在全局拓扑中的表达强度）
        norm_local = np.linalg.norm(local_trunc)
        norm_global = np.linalg.norm(global_trunc)
        if norm_local > 0 and norm_global > 0:
            projection_coeff = np.dot(local_trunc, global_trunc) / (norm_local * norm_global)
        else:
            projection_coeff = 0.0

        # 构造output_dim维的全局组件：
        # 1. 将全局Fiedler向量扩展/截断到output_dim
        # 2. 用投影系数调制，编码局部-全局关联强度
        # 3. 附加谱特征（投影系数的多阶信息）
        global_expanded = np.zeros(self.output_dim)

        # 第一部分：全局Fiedler向量的直接嵌入（调制后）
        embed_len = min(len(global_fiedler), self.output_dim // 2)
        global_expanded[:embed_len] = projection_coeff * global_fiedler[:embed_len]

        # 第二部分：局部-全局交互特征（交叉调制）
        cross_len = min(min_len, self.output_dim - self.output_dim // 2)
        cross_start = self.output_dim // 2
        # 逐元素乘积编码局部与全局的交互模式
        global_expanded[cross_start:cross_start + cross_len] = (
            local_trunc[:cross_len] * global_trunc[:cross_len]
        )

        # 标准化
        norm = np.linalg.norm(global_expanded)
        if norm > 0:
            global_expanded = global_expanded / norm

        return global_expanded
    
    def map_multi_scale(self, laplacian_matrices, global_fiedler=None):
        """
        执行多尺度全息映射
        
        参数:
        - laplacian_matrices: 多个尺度的拉普拉斯矩阵列表
        - global_fiedler: 全局Fiedler向量（可选）
        
        返回:
        - 多尺度全息表示向量
        """
        # 为每个尺度计算全息表示
        multi_scale_reps = []
        scale_weights = []
        
        for i, matrix in enumerate(laplacian_matrices):
            # 计算当前尺度的全息表示
            holographic_rep = self.map_local_to_global(matrix, global_fiedler)
            
            # 计算权重（尺度越大权重越小）
            weight = 1.0 / (self.scale_decay ** i)
            
            multi_scale_reps.append(holographic_rep)
            scale_weights.append(weight)
        
        # 标准化权重
        total_weight = sum(scale_weights)
        if total_weight > 0:
            scale_weights = [w / total_weight for w in scale_weights]
        
        # 加权融合多尺度表示
        weighted_reps = [w * rep for w, rep in zip(scale_weights, multi_scale_reps)]
        fused_rep = np.sum(weighted_reps, axis=0)
        
        # 标准化
        norm = np.linalg.norm(fused_rep)
        if norm > 0:
            fused_rep = fused_rep / norm
        
        return fused_rep