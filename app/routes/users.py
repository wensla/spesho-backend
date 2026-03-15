from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from app import db
from app.models.user import User
from app.middleware.auth import manager_required, login_required

users_bp = Blueprint('users', __name__)


@users_bp.route('/', methods=['GET'])
@manager_required
def list_users():
    users = User.query.all()
    return jsonify({'users': [u.to_dict() for u in users]}), 200


@users_bp.route('/', methods=['POST'])
@manager_required
def create_user():
    data = request.get_json()
    required = ['username', 'password', 'role']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    username = data['username'].strip()
    if len(username) < 3:
        return jsonify({'error': 'username must be at least 3 characters'}), 400

    password = data['password']
    if len(password) < 6:
        return jsonify({'error': 'password must be at least 6 characters'}), 400

    if data['role'] not in ('manager', 'salesperson'):
        return jsonify({'error': 'Role must be manager or salesperson'}), 400

    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 409

    user = User(
        username=username,
        role=data['role'],
        full_name=data.get('full_name', ''),
    )
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    return jsonify({'user': user.to_dict()}), 201


@users_bp.route('/<int:user_id>', methods=['PUT'])
@manager_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    if 'full_name' in data:
        user.full_name = data['full_name']
    if 'role' in data and data['role'] in ('manager', 'salesperson'):
        user.role = data['role']
    if 'is_active' in data:
        user.is_active = data['is_active']
    if 'password' in data and data['password']:
        user.set_password(data['password'])

    db.session.commit()
    return jsonify({'user': user.to_dict()}), 200


@users_bp.route('/<int:user_id>', methods=['DELETE'])
@manager_required
def delete_user(user_id):
    current_id = get_jwt_identity()
    if current_id == user_id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    user = User.query.get_or_404(user_id)
    user.is_active = False
    db.session.commit()
    return jsonify({'message': 'User deactivated'}), 200
