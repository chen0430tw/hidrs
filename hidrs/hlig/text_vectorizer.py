"""
文本向量化器

支持多种向量化方法：
1. TF-IDF
2. 词嵌入 (Word2Vec/BERT)
3. 关键词提取
"""

import logging
import numpy as np
from typing import List, Dict, Any
from collections import Counter
import re

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("sklearn未安装，TF-IDF功能受限")

try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.tokenize import word_tokenize
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False
    logging.warning("nltk未安装，文本处理功能受限")

logger = logging.getLogger(__name__)


class TextVectorizer:
    """文本向量化器"""

    def __init__(self, output_dim: int = 256):
        """
        初始化向量化器

        Args:
            output_dim: 输出向量维度
        """
        self.output_dim = output_dim

        # TF-IDF向量化器
        if SKLEARN_AVAILABLE:
            self.tfidf_vectorizer = TfidfVectorizer(
                max_features=output_dim,
                stop_words='english' if not NLTK_AVAILABLE else None,
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.8,
            )
            self.tfidf_fitted = False
        else:
            self.tfidf_vectorizer = None

        # 停用词
        if NLTK_AVAILABLE:
            try:
                self.stop_words = set(stopwords.words('english'))
            except:
                # 尝试下载
                try:
                    nltk.download('stopwords', quiet=True)
                    nltk.download('punkt', quiet=True)
                    self.stop_words = set(stopwords.words('english'))
                except:
                    self.stop_words = set()
        else:
            # 基础英文停用词
            self.stop_words = {
                'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at',
                'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was',
                'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
                'do', 'does', 'did', 'will', 'would', 'could', 'should',
                'may', 'might', 'can', 'this', 'that', 'these', 'those',
            }

        # 统计信息
        self.stats = {
            'total_vectorized': 0,
            'total_tokens': 0,
        }

    def vectorize_tfidf(self, text: str) -> np.ndarray:
        """
        使用TF-IDF向量化单个文本

        Args:
            text: 文本

        Returns:
            TF-IDF向量 (output_dim,)
        """
        if not SKLEARN_AVAILABLE or not self.tfidf_vectorizer:
            logger.warning("TF-IDF不可用，使用简单词频向量")
            return self._simple_word_frequency_vector(text)

        try:
            # 如果还没有fit，先fit
            if not self.tfidf_fitted:
                self.tfidf_vectorizer.fit([text])
                self.tfidf_fitted = True

            vector = self.tfidf_vectorizer.transform([text]).toarray()[0]

            # 调整维度
            if len(vector) < self.output_dim:
                padding = np.zeros(self.output_dim - len(vector))
                vector = np.concatenate([vector, padding])
            elif len(vector) > self.output_dim:
                vector = vector[:self.output_dim]

            self.stats['total_vectorized'] += 1
            return vector

        except Exception as e:
            logger.debug(f"TF-IDF向量化失败: {e}")
            return self._simple_word_frequency_vector(text)

    def vectorize_embedding(self, text: str) -> np.ndarray:
        """
        使用词嵌入向量化文本

        尝试加载顺序：
        1. sentence-transformers（效果最好，支持中文）
        2. gensim Word2Vec（英文为主）
        3. 回退到TF-IDF（明确警告）

        Args:
            text: 文本

        Returns:
            嵌入向量 (output_dim,)
        """
        if not text or not text.strip():
            return np.zeros(self.output_dim)

        # 延迟加载嵌入模型（只初始化一次）
        if not hasattr(self, '_embedding_model'):
            self._embedding_model = None
            self._embedding_type = None

            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer(
                    'paraphrase-multilingual-MiniLM-L12-v2'
                )
                self._embedding_type = 'sentence_transformer'
                logger.info("[TextVectorizer] 已加载sentence-transformers模型")
            except (ImportError, Exception):
                pass

            if self._embedding_model is None:
                try:
                    import gensim.downloader as api
                    self._embedding_model = api.load('word2vec-google-news-300')
                    self._embedding_type = 'word2vec'
                    logger.info("[TextVectorizer] 已加载Word2Vec模型")
                except (ImportError, Exception):
                    pass

            if self._embedding_model is None:
                logger.warning(
                    "[TextVectorizer] 无可用词嵌入模型"
                    "（需要 sentence-transformers 或 gensim），回退到TF-IDF"
                )

        # sentence-transformers路径
        if self._embedding_type == 'sentence_transformer':
            try:
                vec = self._embedding_model.encode(text)
                if len(vec) > self.output_dim:
                    vec = vec[:self.output_dim]
                elif len(vec) < self.output_dim:
                    vec = np.concatenate([vec, np.zeros(self.output_dim - len(vec))])
                self.stats['total_vectorized'] += 1
                return vec
            except Exception as e:
                logger.debug(f"sentence-transformers编码失败: {e}")

        # Word2Vec路径（词向量平均）
        if self._embedding_type == 'word2vec':
            try:
                tokens = self.tokenize(text)
                vectors = [
                    self._embedding_model[t] for t in tokens
                    if t in self._embedding_model
                ]
                if vectors:
                    vec = np.mean(vectors, axis=0)
                    if len(vec) > self.output_dim:
                        vec = vec[:self.output_dim]
                    elif len(vec) < self.output_dim:
                        vec = np.concatenate([vec, np.zeros(self.output_dim - len(vec))])
                    self.stats['total_vectorized'] += 1
                    return vec
            except Exception as e:
                logger.debug(f"Word2Vec编码失败: {e}")

        # 回退到TF-IDF
        return self.vectorize_tfidf(text)

    def vectorize_batch(
        self,
        texts: List[str],
        method: str = 'tfidf'
    ) -> np.ndarray:
        """
        批量向量化文本（优化版）

        Args:
            texts: 文本列表
            method: 向量化方法

        Returns:
            向量矩阵 (n_texts, output_dim)
        """
        if not texts:
            return np.array([])

        if method == 'tfidf' and SKLEARN_AVAILABLE and self.tfidf_vectorizer:
            try:
                # 批量fit和transform
                if not self.tfidf_fitted:
                    self.tfidf_vectorizer.fit(texts)
                    self.tfidf_fitted = True

                vectors = self.tfidf_vectorizer.transform(texts).toarray()

                # 调整维度
                if vectors.shape[1] < self.output_dim:
                    padding = np.zeros((len(texts), self.output_dim - vectors.shape[1]))
                    vectors = np.hstack([vectors, padding])
                elif vectors.shape[1] > self.output_dim:
                    vectors = vectors[:, :self.output_dim]

                self.stats['total_vectorized'] += len(texts)
                return vectors

            except Exception as e:
                logger.warning(f"批量TF-IDF失败: {e}，使用逐个处理")

        # 逐个处理（备用）
        vectors = []
        for text in texts:
            if method == 'tfidf':
                vector = self.vectorize_tfidf(text)
            elif method == 'embedding':
                vector = self.vectorize_embedding(text)
            else:
                vector = np.zeros(self.output_dim)
            vectors.append(vector)

        return np.array(vectors)

    def _simple_word_frequency_vector(self, text: str) -> np.ndarray:
        """
        简单的词频向量（TF-IDF的备用方案）

        Args:
            text: 文本

        Returns:
            词频向量 (output_dim,)
        """
        tokens = self.tokenize(text)
        if not tokens:
            return np.zeros(self.output_dim)

        # 统计词频
        word_freq = Counter(tokens)

        # 取前output_dim个高频词
        top_words = word_freq.most_common(self.output_dim)

        # 构建向量
        vector = np.zeros(self.output_dim)
        for i, (word, freq) in enumerate(top_words):
            vector[i] = freq

        # 归一化
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector

    def tokenize(self, text: str) -> List[str]:
        """
        分词（支持中英文）

        Args:
            text: 文本

        Returns:
            词列表
        """
        if not text:
            return []

        # 转小写
        text = text.lower()

        # 基础分词（英文）
        if NLTK_AVAILABLE:
            try:
                tokens = word_tokenize(text)
            except:
                # 简单分词
                tokens = re.findall(r'\b\w+\b', text)
        else:
            # 简单分词
            tokens = re.findall(r'\b\w+\b', text)

        # 过滤停用词和短词
        tokens = [
            token for token in tokens
            if token not in self.stop_words and len(token) > 2
        ]

        self.stats['total_tokens'] += len(tokens)
        return tokens

    def extract_keywords(
        self,
        text: str,
        top_n: int = 10
    ) -> List[str]:
        """
        提取关键词（基于词频）

        Args:
            text: 文本
            top_n: 返回前N个关键词

        Returns:
            关键词列表
        """
        tokens = self.tokenize(text)
        if not tokens:
            return []

        # 统计词频
        word_freq = Counter(tokens)

        # 返回高频词
        keywords = [word for word, freq in word_freq.most_common(top_n)]

        return keywords

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'total_vectorized': self.stats['total_vectorized'],
            'total_tokens': self.stats['total_tokens'],
            'tfidf_available': SKLEARN_AVAILABLE,
            'nltk_available': NLTK_AVAILABLE,
            'stop_words_count': len(self.stop_words),
        }
