"""
LLM辅助数据分析API
"""
import os
import json
import logging
import requests
from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger(__name__)
llm_bp = Blueprint('llm', __name__)

# Prompt模板
PROMPTS = {
    'email_cluster': """分析以下邮箱域名数据，识别可能属于同一组织或关联的域名群组：
{data}
请用中文Markdown格式输出聚类分析报告。""",

    'password_pattern': """分析以下密码数据的模式和规律：
{data}
请识别常见模式、弱密码特征，并给出安全建议。用中文Markdown格式输出。""",

    'data_source_infer': """基于以下数据特征推断可能的数据来源：
{data}
请分析数据格式、字段特征、时间分布等信息，推断可能的泄露来源。用中文Markdown格式输出。""",

    'risk_report': """基于以下数据统计信息生成风险评估报告：
{data}
请从数据泄露规模、影响范围、密码安全性、时间分布等维度分析，用中文Markdown格式输出专业的风险评估报告。""",

    'general': """基于以下数据分析需求进行分析：
问题: {question}
数据: {data}
请用中文Markdown格式输出分析结果。"""
}


def _call_llm(prompt, api_key=None, model='gpt-3.5-turbo', base_url=None):
    """调用LLM API"""
    api_key = api_key or os.getenv('LLM_API_KEY', '')
    base_url = base_url or os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1')
    
    if not api_key:
        return None, "未配置LLM API密钥"
    
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': model,
                'messages': [
                    {'role': 'system', 'content': '你是一位专业的数据安全分析师。'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 2000,
                'temperature': 0.7
            },
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            return content, None
        else:
            return None, f"API请求失败: {response.status_code}"
    except Exception as e:
        return None, f"LLM调用异常: {str(e)}"


@llm_bp.route('/llm/analyze', methods=['POST'])
def llm_analyze():
    """LLM辅助分析"""
    try:
        data = request.get_json()
        analysis_type = data.get('type', 'general')
        input_data = data.get('data', '')
        question = data.get('question', '')
        
        # 选择prompt模板
        if analysis_type in PROMPTS:
            prompt = PROMPTS[analysis_type].format(data=input_data, question=question)
        else:
            prompt = PROMPTS['general'].format(data=input_data, question=question)
        
        # 调用LLM
        result, error = _call_llm(prompt)
        
        if error:
            return jsonify({'status': 'error', 'message': error}), 500
        
        return jsonify({
            'status': 'ok',
            'data': {
                'analysis': result,
                'type': analysis_type
            }
        })
    except Exception as e:
        logger.error(f"LLM分析错误: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@llm_bp.route('/llm/templates', methods=['GET'])
def get_templates():
    """获取可用的分析模板"""
    templates = [
        {'id': 'email_cluster', 'name': '邮箱域名聚类', 'description': '分析邮箱域名的关联关系'},
        {'id': 'password_pattern', 'name': '密码模式分析', 'description': '分析密码规律和安全性'},
        {'id': 'data_source_infer', 'name': '数据源推断', 'description': '推断数据泄露来源'},
        {'id': 'risk_report', 'name': '风险评估报告', 'description': '生成数据泄露风险评估'},
        {'id': 'general', 'name': '自定义分析', 'description': '自定义分析问题'}
    ]
    return jsonify({'status': 'ok', 'data': templates})


def register_llm_routes(app):
    app.register_blueprint(llm_bp, url_prefix='/api')
