"""
计算工作节点 - 执行分布式计算任务

功能：
1. 接收任务
2. 执行计算
3. 报告进度
4. 返回结果

工作模式：
- Pull模式：主动从调度器拉取任务
- Push模式：被动接收调度器推送的任务

安全考虑：
- 沙箱执行（限制资源访问）
- 超时控制
- 异常捕获
"""
import logging
import time
import threading
import multiprocessing
from typing import Optional, Callable, Dict, Any
from enum import Enum
from datetime import datetime
import traceback

logger = logging.getLogger(__name__)


class WorkerStatus(Enum):
    """工作节点状态"""
    IDLE = "idle"              # 空闲
    WORKING = "working"        # 工作中
    ERROR = "error"            # 错误
    STOPPED = "stopped"        # 已停止


class ComputeWorker:
    """计算工作节点"""

    def __init__(
        self,
        worker_id: str,
        max_concurrent_tasks: int = 1,
        timeout_seconds: int = 3600,
        report_interval: int = 10
    ):
        """
        初始化计算工作节点

        参数:
        - worker_id: 工作节点ID
        - max_concurrent_tasks: 最大并发任务数
        - timeout_seconds: 任务超时时间（秒）
        - report_interval: 进度报告间隔（秒）
        """
        self.worker_id = worker_id
        self.max_concurrent_tasks = max_concurrent_tasks
        self.timeout_seconds = timeout_seconds
        self.report_interval = report_interval

        self.status = WorkerStatus.IDLE
        self.current_tasks: Dict[str, Any] = {}  # 当前运行的任务
        self.completed_tasks = 0
        self.failed_tasks = 0

        self._stop_flag = False
        self._task_threads: Dict[str, threading.Thread] = {}

        # 注册的函数（名称 -> 可调用对象）
        self.registered_functions: Dict[str, Callable] = {}

        logger.info(f"[ComputeWorker-{worker_id}] 初始化完成")
        logger.info(f"  最大并发任务: {max_concurrent_tasks}")
        logger.info(f"  超时时间: {timeout_seconds}秒")

    def register_function(self, name: str, func: Callable):
        """
        注册可执行函数

        参数:
        - name: 函数名
        - func: 可调用对象
        """
        self.registered_functions[name] = func
        logger.info(f"[ComputeWorker-{self.worker_id}] 注册函数: {name}")

    def execute_task(self, task) -> Dict:
        """
        执行任务

        参数:
        - task: ComputeTask对象

        返回:
        - 执行结果 {'success': bool, 'result': any, 'error': str}
        """
        if len(self.current_tasks) >= self.max_concurrent_tasks:
            logger.warning(f"[ComputeWorker-{self.worker_id}] 达到最大并发数，拒绝任务 {task.task_id}")
            return {
                'success': False,
                'error': 'Worker at max capacity'
            }

        logger.info(f"[ComputeWorker-{self.worker_id}] 开始执行任务: {task.task_id}")

        # 启动任务线程
        task_thread = threading.Thread(
            target=self._execute_task_thread,
            args=(task,),
            daemon=True
        )
        task_thread.start()

        self._task_threads[task.task_id] = task_thread
        self.current_tasks[task.task_id] = {
            'task': task,
            'start_time': datetime.now(),
            'status': 'running'
        }

        self.status = WorkerStatus.WORKING

        return {
            'success': True,
            'message': 'Task started'
        }

    def _execute_task_thread(self, task):
        """任务执行线程"""
        result = None
        error = None
        success = False

        try:
            # 1. 获取函数
            func = self.registered_functions.get(task.function_name)
            if not func:
                raise ValueError(f"未注册的函数: {task.function_name}")

            # 2. 执行函数（带超时）
            start_time = time.time()
            result = self._execute_with_timeout(
                func,
                task.args,
                task.kwargs,
                timeout=self.timeout_seconds
            )
            elapsed = time.time() - start_time

            success = True
            logger.info(f"[ComputeWorker-{self.worker_id}] 任务完成: {task.task_id} (耗时: {elapsed:.2f}秒)")

        except TimeoutError:
            error = f"任务超时（>{self.timeout_seconds}秒）"
            logger.error(f"[ComputeWorker-{self.worker_id}] 任务超时: {task.task_id}")

        except Exception as e:
            error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"[ComputeWorker-{self.worker_id}] 任务失败: {task.task_id} - {error}")

        finally:
            # 3. 更新任务状态
            if task.task_id in self.current_tasks:
                self.current_tasks[task.task_id]['status'] = 'completed' if success else 'failed'
                self.current_tasks[task.task_id]['result'] = result
                self.current_tasks[task.task_id]['error'] = error
                self.current_tasks[task.task_id]['end_time'] = datetime.now()

            if success:
                self.completed_tasks += 1
            else:
                self.failed_tasks += 1

            # 4. 检查是否所有任务完成
            if all(info['status'] in ['completed', 'failed']
                   for info in self.current_tasks.values()):
                self.status = WorkerStatus.IDLE

    def _execute_with_timeout(self, func: Callable, args: tuple, kwargs: dict, timeout: int) -> Any:
        """
        带超时的函数执行

        使用multiprocessing实现超时控制
        """
        # 使用进程池执行（可以强制终止）
        with multiprocessing.Pool(processes=1) as pool:
            async_result = pool.apply_async(func, args, kwargs)
            try:
                result = async_result.get(timeout=timeout)
                return result
            except multiprocessing.TimeoutError:
                pool.terminate()
                raise TimeoutError(f"Function execution exceeded {timeout} seconds")

    def get_task_result(self, task_id: str) -> Optional[Dict]:
        """
        获取任务结果

        返回:
        - 任务结果信息，如果任务不存在返回None
        """
        task_info = self.current_tasks.get(task_id)
        if not task_info:
            return None

        return {
            'task_id': task_id,
            'status': task_info['status'],
            'result': task_info.get('result'),
            'error': task_info.get('error'),
            'start_time': task_info['start_time'].isoformat(),
            'end_time': task_info.get('end_time').isoformat() if task_info.get('end_time') else None
        }

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        注意：由于Python的GIL和多线程限制，强制取消任务比较困难
        这里只标记任务为已取消，实际执行可能还会继续
        """
        if task_id not in self.current_tasks:
            return False

        self.current_tasks[task_id]['status'] = 'cancelled'
        logger.info(f"[ComputeWorker-{self.worker_id}] 任务已标记为取消: {task_id}")

        return True

    def stop(self):
        """停止工作节点"""
        self._stop_flag = True
        self.status = WorkerStatus.STOPPED

        # 等待所有任务完成
        for thread in self._task_threads.values():
            if thread.is_alive():
                thread.join(timeout=5)

        logger.info(f"[ComputeWorker-{self.worker_id}] 已停止")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'worker_id': self.worker_id,
            'status': self.status.value,
            'current_tasks': len(self.current_tasks),
            'max_concurrent_tasks': self.max_concurrent_tasks,
            'completed_tasks': self.completed_tasks,
            'failed_tasks': self.failed_tasks,
            'success_rate': self.completed_tasks / (self.completed_tasks + self.failed_tasks)
                           if (self.completed_tasks + self.failed_tasks) > 0 else 0,
            'registered_functions': list(self.registered_functions.keys())
        }


# 示例：定义一些可以分布式执行的函数

def example_matrix_multiply(A, B):
    """示例：矩阵乘法"""
    import numpy as np
    return np.dot(A, B)


def example_prime_check(n):
    """示例：质数检查"""
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True


def example_monte_carlo_pi(iterations):
    """示例：蒙特卡洛法计算π"""
    import random
    inside_circle = 0

    for _ in range(iterations):
        x = random.random()
        y = random.random()
        if x**2 + y**2 <= 1:
            inside_circle += 1

    return 4.0 * inside_circle / iterations


def example_fibonacci(n):
    """示例：计算斐波那契数列"""
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


# 注册示例函数的辅助函数
def register_example_functions(worker: ComputeWorker):
    """注册示例函数到工作节点"""
    worker.register_function('matrix_multiply', example_matrix_multiply)
    worker.register_function('prime_check', example_prime_check)
    worker.register_function('monte_carlo_pi', example_monte_carlo_pi)
    worker.register_function('fibonacci', example_fibonacci)
    logger.info(f"[ComputeWorker-{worker.worker_id}] 注册了 4 个示例函数")
