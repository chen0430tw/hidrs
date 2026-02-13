"""
格式模板API
"""
import os
import json
import uuid
import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)
format_bp = Blueprint('format_templates', __name__)

TEMPLATES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'configs', 'templates.json')

def _load_templates():
    if os.path.exists(TEMPLATES_FILE):
        with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def _save_templates(templates):
    os.makedirs(os.path.dirname(TEMPLATES_FILE), exist_ok=True)
    with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)

@format_bp.route('/admin/config/templates', methods=['GET'])
def list_templates():
    return jsonify({'status': 'ok', 'data': _load_templates()})

@format_bp.route('/admin/config/templates', methods=['POST'])
def create_template():
    data = request.get_json()
    data['id'] = str(uuid.uuid4())[:8]
    templates = _load_templates()
    templates.append(data)
    _save_templates(templates)
    return jsonify({'status': 'ok', 'data': data})

@format_bp.route('/admin/config/templates/<template_id>', methods=['PUT'])
def update_template(template_id):
    data = request.get_json()
    templates = _load_templates()
    for i, t in enumerate(templates):
        if t.get('id') == template_id:
            data['id'] = template_id
            templates[i] = data
            _save_templates(templates)
            return jsonify({'status': 'ok', 'data': data})
    return jsonify({'status': 'error', 'message': '模板不存在'}), 404

@format_bp.route('/admin/config/templates/<template_id>', methods=['DELETE'])
def delete_template(template_id):
    templates = _load_templates()
    templates = [t for t in templates if t.get('id') != template_id]
    _save_templates(templates)
    return jsonify({'status': 'ok'})

def register_format_routes(app):
    app.register_blueprint(format_bp, url_prefix='/api')
