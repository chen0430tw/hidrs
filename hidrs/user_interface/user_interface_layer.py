"""
用户交互与展示层 - 整合Web界面和API服务
"""
import threading
from .api_server import ApiServer


class UserInterfaceLayer:
    """用户交互与展示层，整合Web界面和API服务"""
    
    def __init__(self):
        """初始化用户界面层"""
        self.api_server = None
        self.server_thread = None
        self.running = False
    
    def start(self, host='0.0.0.0', port=5000, debug=False):
        """启动用户界面层服务"""
        self.running = True
        
        # 创建API服务器
        self.api_server = ApiServer()
        
        if debug:
            # 在主线程中运行（便于调试）
            self.api_server.start(host, port, debug)
        else:
            # 在单独线程中运行
            self.server_thread = threading.Thread(
                target=self.api_server.start,
                args=(host, port, False),
                daemon=True
            )
            self.server_thread.start()
        
        print(f"User interface layer started on http://{host}:{port}")
    
    def stop(self):
        """停止用户界面层服务"""
        self.running = False
        
        if self.api_server:
            self.api_server.shutdown()
        
        print("User interface layer stopped")