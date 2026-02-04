"""
爬虫限流器 - 防止服务器容量被塞爆
支持多种限流策略：令牌桶、漏桶、固定窗口、滑动窗口
"""
import time
import threading
from collections import deque
from datetime import datetime, timedelta


class RateLimiter:
    """
    通用限流器基类
    """
    def acquire(self, tokens=1):
        """获取令牌，返回是否成功"""
        raise NotImplementedError

    def wait_and_acquire(self, tokens=1, timeout=None):
        """等待并获取令牌"""
        raise NotImplementedError


class TokenBucketLimiter(RateLimiter):
    """
    令牌桶限流器（推荐）
    - 容量：桶的最大令牌数
    - 速率：每秒生成的令牌数
    - 支持突发流量，平滑限流
    """
    def __init__(self, capacity, refill_rate):
        """
        参数:
        - capacity: 桶容量（最大令牌数）
        - refill_rate: 令牌生成速率（每秒）
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = threading.Lock()

    def _refill(self):
        """补充令牌"""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate

        if tokens_to_add > 0:
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_refill = now

    def acquire(self, tokens=1):
        """尝试获取令牌"""
        with self.lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def wait_and_acquire(self, tokens=1, timeout=None):
        """等待并获取令牌"""
        start_time = time.time()

        while True:
            if self.acquire(tokens):
                return True

            # 检查超时
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False

            # 计算需要等待的时间
            with self.lock:
                self._refill()
                if self.tokens >= tokens:
                    continue

                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.refill_rate
                time.sleep(min(wait_time, 0.1))  # 最多等待0.1秒再检查


class SlidingWindowLimiter(RateLimiter):
    """
    滑动窗口限流器
    - 精确控制时间窗口内的请求数
    - 内存占用：O(请求数)
    """
    def __init__(self, max_requests, window_seconds):
        """
        参数:
        - max_requests: 时间窗口内最大请求数
        - window_seconds: 时间窗口大小（秒）
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()  # 存储请求时间戳
        self.lock = threading.Lock()

    def _clean_old_requests(self, now):
        """清理过期的请求记录"""
        cutoff_time = now - self.window_seconds
        while self.requests and self.requests[0] < cutoff_time:
            self.requests.popleft()

    def acquire(self, tokens=1):
        """尝试获取令牌"""
        with self.lock:
            now = time.time()
            self._clean_old_requests(now)

            if len(self.requests) + tokens <= self.max_requests:
                for _ in range(tokens):
                    self.requests.append(now)
                return True
            return False

    def wait_and_acquire(self, tokens=1, timeout=None):
        """等待并获取令牌"""
        start_time = time.time()

        while True:
            if self.acquire(tokens):
                return True

            # 检查超时
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False

            # 计算需要等待的时间
            with self.lock:
                now = time.time()
                self._clean_old_requests(now)

                if len(self.requests) + tokens <= self.max_requests:
                    continue

                # 等待最旧的请求过期
                if self.requests:
                    oldest_request = self.requests[0]
                    wait_time = oldest_request + self.window_seconds - now
                    time.sleep(max(0.1, wait_time))
                else:
                    time.sleep(0.1)


class CrawlerRateLimiter:
    """
    爬虫专用限流器（组合多种限流策略）
    """
    def __init__(self, config):
        """
        参数:
        - config: 限流配置字典
        """
        self.config = config
        self.enabled = config.get('enabled', True)

        if not self.enabled:
            return

        # 全局限流器（令牌桶）
        global_config = config.get('global', {})
        self.global_limiter = TokenBucketLimiter(
            capacity=global_config.get('burst_capacity', 100),
            refill_rate=global_config.get('requests_per_second', 10)
        )

        # 域名级别限流器（滑动窗口）
        domain_config = config.get('per_domain', {})
        self.domain_limiters = {}
        self.domain_max_requests = domain_config.get('max_requests', 30)
        self.domain_window_seconds = domain_config.get('window_seconds', 60)
        self.domain_limiters_lock = threading.Lock()

        # MongoDB写入限流器
        mongo_config = config.get('mongodb', {})
        self.mongo_limiter = TokenBucketLimiter(
            capacity=mongo_config.get('burst_capacity', 500),
            refill_rate=mongo_config.get('writes_per_second', 50)
        )

        # Kafka发送限流器
        kafka_config = config.get('kafka', {})
        self.kafka_limiter = TokenBucketLimiter(
            capacity=kafka_config.get('burst_capacity', 1000),
            refill_rate=kafka_config.get('messages_per_second', 100)
        )

        # 统计信息
        self.stats = {
            'total_requests': 0,
            'blocked_requests': 0,
            'mongo_writes': 0,
            'kafka_messages': 0,
            'blocked_mongo': 0,
            'blocked_kafka': 0
        }
        self.stats_lock = threading.Lock()

    def _get_domain(self, url):
        """从URL提取域名"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return url

    def _get_domain_limiter(self, domain):
        """获取或创建域名限流器"""
        with self.domain_limiters_lock:
            if domain not in self.domain_limiters:
                self.domain_limiters[domain] = SlidingWindowLimiter(
                    max_requests=self.domain_max_requests,
                    window_seconds=self.domain_window_seconds
                )
            return self.domain_limiters[domain]

    def acquire_for_url(self, url, timeout=None):
        """
        为URL请求获取令牌
        返回: (success: bool, wait_time: float)
        """
        if not self.enabled:
            return True, 0

        start_time = time.time()

        # 1. 全局限流
        if not self.global_limiter.wait_and_acquire(tokens=1, timeout=timeout):
            with self.stats_lock:
                self.stats['blocked_requests'] += 1
            return False, time.time() - start_time

        # 2. 域名限流
        domain = self._get_domain(url)
        domain_limiter = self._get_domain_limiter(domain)

        remaining_timeout = None
        if timeout is not None:
            remaining_timeout = timeout - (time.time() - start_time)
            if remaining_timeout <= 0:
                with self.stats_lock:
                    self.stats['blocked_requests'] += 1
                return False, time.time() - start_time

        if not domain_limiter.wait_and_acquire(tokens=1, timeout=remaining_timeout):
            with self.stats_lock:
                self.stats['blocked_requests'] += 1
            return False, time.time() - start_time

        with self.stats_lock:
            self.stats['total_requests'] += 1

        return True, time.time() - start_time

    def acquire_for_mongo(self, timeout=None):
        """为MongoDB写入获取令牌"""
        if not self.enabled:
            return True

        if self.mongo_limiter.wait_and_acquire(tokens=1, timeout=timeout):
            with self.stats_lock:
                self.stats['mongo_writes'] += 1
            return True
        else:
            with self.stats_lock:
                self.stats['blocked_mongo'] += 1
            return False

    def acquire_for_kafka(self, timeout=None):
        """为Kafka发送获取令牌"""
        if not self.enabled:
            return True

        if self.kafka_limiter.wait_and_acquire(tokens=1, timeout=timeout):
            with self.stats_lock:
                self.stats['kafka_messages'] += 1
            return True
        else:
            with self.stats_lock:
                self.stats['blocked_kafka'] += 1
            return False

    def get_stats(self):
        """获取限流统计"""
        with self.stats_lock:
            return self.stats.copy()

    def reset_stats(self):
        """重置统计"""
        with self.stats_lock:
            self.stats = {
                'total_requests': 0,
                'blocked_requests': 0,
                'mongo_writes': 0,
                'kafka_messages': 0,
                'blocked_mongo': 0,
                'blocked_kafka': 0
            }


# 预设配置
RATE_LIMIT_CONFIGS = {
    # 低强度（开发/测试）
    'low': {
        'enabled': True,
        'global': {
            'burst_capacity': 50,
            'requests_per_second': 5
        },
        'per_domain': {
            'max_requests': 10,
            'window_seconds': 60
        },
        'mongodb': {
            'burst_capacity': 200,
            'writes_per_second': 20
        },
        'kafka': {
            'burst_capacity': 500,
            'messages_per_second': 50
        }
    },

    # 中等强度（生产环境）
    'medium': {
        'enabled': True,
        'global': {
            'burst_capacity': 100,
            'requests_per_second': 10
        },
        'per_domain': {
            'max_requests': 30,
            'window_seconds': 60
        },
        'mongodb': {
            'burst_capacity': 500,
            'writes_per_second': 50
        },
        'kafka': {
            'burst_capacity': 1000,
            'messages_per_second': 100
        }
    },

    # 高强度（高性能服务器）
    'high': {
        'enabled': True,
        'global': {
            'burst_capacity': 200,
            'requests_per_second': 20
        },
        'per_domain': {
            'max_requests': 50,
            'window_seconds': 60
        },
        'mongodb': {
            'burst_capacity': 1000,
            'writes_per_second': 100
        },
        'kafka': {
            'burst_capacity': 2000,
            'messages_per_second': 200
        }
    },

    # 无限制（禁用限流）
    'unlimited': {
        'enabled': False
    }
}


if __name__ == '__main__':
    # 测试代码
    print("测试令牌桶限流器...")
    limiter = TokenBucketLimiter(capacity=10, refill_rate=2)

    for i in range(15):
        success = limiter.acquire(1)
        print(f"请求 {i+1}: {'成功' if success else '失败'} (剩余令牌: {limiter.tokens:.2f})")
        time.sleep(0.5)

    print("\n测试滑动窗口限流器...")
    window_limiter = SlidingWindowLimiter(max_requests=5, window_seconds=2)

    for i in range(8):
        success = window_limiter.acquire(1)
        print(f"请求 {i+1}: {'成功' if success else '失败'}")
        time.sleep(0.3)

    print("\n测试爬虫限流器...")
    crawler_limiter = CrawlerRateLimiter(RATE_LIMIT_CONFIGS['low'])

    for i in range(10):
        success, wait_time = crawler_limiter.acquire_for_url('https://example.com/page', timeout=5)
        print(f"URL请求 {i+1}: {'成功' if success else '失败'} (等待: {wait_time:.3f}秒)")
        time.sleep(0.1)

    print(f"\n统计信息: {crawler_limiter.get_stats()}")
