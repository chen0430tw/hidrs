"""工具API模块"""
from .mobile_lookup import register_mobile_routes
from .idcard_lookup import register_idcard_routes
from .generator import register_generator_routes

def register_tools_routes(app):
    register_mobile_routes(app)
    register_idcard_routes(app)
    register_generator_routes(app)
