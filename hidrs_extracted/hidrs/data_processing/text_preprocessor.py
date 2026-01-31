"""
文本预处理类，负责文本清洗和标准化
"""
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer


class TextPreprocessor:
    """文本预处理类，负责文本清洗和标准化"""
    
    def __init__(self):
        # 确保NLTK数据包已下载
        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download('stopwords')
        
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt')
        
        try:
            nltk.data.find('corpora/wordnet')
        except LookupError:
            nltk.download('wordnet')
        
        # 初始化NLTK组件
        self.stop_words = set(stopwords.words('english'))
        self.lemmatizer = WordNetLemmatizer()
    
    def clean_text(self, text):
        """清洗文本：小写化、标记化、去除停用词、词形还原"""
        if not text or not isinstance(text, str):
            return ""
        
        # 转换为小写
        text = text.lower()
        
        # 分词
        tokens = word_tokenize(text)
        
        # 去除停用词和非字母字符
        tokens = [token for token in tokens if token.isalpha() and token not in self.stop_words]
        
        # 词形还原
        tokens = [self.lemmatizer.lemmatize(token) for token in tokens]
        
        # 重新组合为文本
        cleaned_text = ' '.join(tokens)
        
        return cleaned_text
    
    def process_html_content(self, html_content):
        """处理HTML内容，提取文本并清洗"""
        # 使用BeautifulSoup提取文本内容
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 获取所有文本
            text = soup.get_text(separator=' ', strip=True)
            
            # 清洗文本
            cleaned_text = self.clean_text(text)
            
            return cleaned_text
        except Exception as e:
            print(f"Error processing HTML: {str(e)}")
            return self.clean_text(html_content)