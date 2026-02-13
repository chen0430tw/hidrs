"""
银狼数据安全平台 - 后端插件基类
"""
from abc import ABC
from flask import Blueprint


class PluginBase(ABC):
    """插件基类"""
    
    id = ''
    name = ''
    version = '1.0.0'
    description = ''
    author = ''
    requires = []
    
    def __init__(self):
        self.enabled = True
        self._blueprint = None
    
    @property
    def blueprint(self):
        if self._blueprint is None:
            self._blueprint = Blueprint(
                self.id,
                __name__,
                url_prefix=f'/api/plugins/{self.id}'
            )
            self.register_routes(self._blueprint)
        return self._blueprint
    
    def register_routes(self, bp):
        """注册插件路由 - 子类实现"""
        pass
    
    def init_app(self, app):
        """初始化插件 - 子类可覆盖"""
        if self._blueprint:
            app.register_blueprint(self.blueprint)
    
    def activate(self):
        self.enabled = True
    
    def deactivate(self):
        self.enabled = False
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'author': self.author,
            'enabled': self.enabled,
            'requires': self.requires
        }
