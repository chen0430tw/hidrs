"""
降维处理类，使用UMAP、PCA等技术进行降维
"""
import os
import json
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
try:
    import umap
    HAS_UMAP = True
except ImportError:
    HAS_UMAP = False


class DimensionalityReducer:
    """降维处理类，使用UMAP、PCA等技术进行降维"""

    def __init__(self, method='umap', config_path="config/dimension_reducer_config.json"):
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.method = method
        self.fitted = False

        # 初始化标准化器
        self.scaler = StandardScaler()

        # 根据方法初始化降维器
        if method == 'umap':
            if not HAS_UMAP:
                raise ImportError("umap-learn 未安装，请运行: pip install umap-learn")
            self.reducer = umap.UMAP(
                n_neighbors=self.config['umap_n_neighbors'],
                min_dist=self.config['umap_min_dist'],
                n_components=self.config['umap_n_components'],
                random_state=42
            )
        elif method == 'pca':
            self.reducer = PCA(
                n_components=self.config['pca_n_components'],
                random_state=42
            )
        else:
            raise ValueError(f"Unsupported reduction method: {method}")
    
    def fit(self, data):
        """训练降维模型"""
        if len(data) < 2:
            print("Not enough data points for fitting. Need at least 2.")
            return
        
        # 标准化数据
        scaled_data = self.scaler.fit_transform(data)
        
        # 训练降维模型
        self.reducer.fit(scaled_data)
        self.fitted = True
        
        print(f"Fitted {self.method} reducer with {len(data)} data points")
    
    def transform(self, data):
        """应用降维模型"""
        if not self.fitted:
            raise ValueError("Reducer not fitted. Call fit() first.")
        
        # 标准化数据
        scaled_data = self.scaler.transform(data)
        
        # 应用降维
        reduced_data = self.reducer.transform(scaled_data)
        
        return reduced_data
    
    def fit_transform(self, data):
        """训练并应用降维模型"""
        if len(data) < 2:
            print("Not enough data points for fitting. Need at least 2.")
            # 返回空数组，保持输入维度但没有样本
            return np.array([]).reshape(0, self.config[f'{self.method}_n_components'])
        
        # 标准化数据
        scaled_data = self.scaler.fit_transform(data)
        
        # 训练并应用降维
        reduced_data = self.reducer.fit_transform(scaled_data)
        self.fitted = True
        
        return reduced_data
    
    def save_model(self, filepath):
        """保存训练好的降维模型"""
        import joblib
        if not self.fitted:
            raise ValueError("Reducer not fitted. Cannot save unfitted model.")
        
        # 创建模型目录
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # 保存模型
        joblib.dump({'reducer': self.reducer, 'scaler': self.scaler}, filepath)
        print(f"Saved reducer model to {filepath}")
    
    def load_model(self, filepath):
        """加载训练好的降维模型"""
        import joblib
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Model file not found: {filepath}")
        
        # 加载模型
        model_data = joblib.load(filepath)
        self.reducer = model_data['reducer']
        self.scaler = model_data['scaler']
        self.fitted = True
        
        print(f"Loaded reducer model from {filepath}")