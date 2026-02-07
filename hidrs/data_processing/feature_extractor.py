"""
特征提取类，负责将文本转换为高维特征向量
支持 BERT (PyTorch) 和 Universal Sentence Encoder (TensorFlow) 两种后端
依赖按需导入，避免未安装的后端阻塞启动
"""
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """特征提取类，负责将文本转换为高维特征向量"""

    def __init__(self, model_type='bert', config_path="config/feature_extractor_config.json"):
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.model_type = model_type
        self._torch = None  # 延迟引用

        # 加载模型
        if model_type == 'bert':
            # 使用BERT模型（PyTorch + Transformers）
            import torch
            from transformers import BertModel, BertTokenizer
            self._torch = torch
            self.tokenizer = BertTokenizer.from_pretrained(self.config['bert_model'])
            self.model = BertModel.from_pretrained(self.config['bert_model'])
            # 设置为评估模式
            self.model.eval()
        elif model_type == 'universal_sentence_encoder':
            # 使用Universal Sentence Encoder（TensorFlow + TF Hub）
            import tensorflow_hub as hub
            self.model = hub.load(self.config['use_model'])
        else:
            raise ValueError(f"Unsupported model type: {model_type}")

    def extract_features(self, text):
        """从文本中提取特征向量"""
        if not text or not isinstance(text, str):
            # 返回零向量
            return np.zeros(self.config['feature_dim'])

        if self.model_type == 'bert':
            # 使用BERT提取特征
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=self.config['max_sequence_length']
            )

            with self._torch.no_grad():
                outputs = self.model(**inputs)

            # 使用[CLS]标记的最后隐藏状态作为特征向量
            embeddings = outputs.last_hidden_state[:, 0, :].numpy()
            return embeddings[0]  # 返回第一个样本的特征向量

        elif self.model_type == 'universal_sentence_encoder':
            # 使用Universal Sentence Encoder提取特征
            embeddings = self.model([text]).numpy()
            return embeddings[0]  # 返回第一个样本的特征向量
