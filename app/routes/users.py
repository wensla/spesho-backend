from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from app import db
from app.models.user import User
from app.models.shop import Shop
from app.middleware.auth import manager_required, super_admin_required, login_required, get_current_user

users_bp = Blueprint('users', __name__)

_VALID_ROLES = ('super_admin', 'manager', 'seller', 'salesperson')


@users_bp.route('/', methods=['GET'])
@manager_required
def list_users():
    current = get_current_user()
    if current.is_super_admin:
        users = User.query.all()
    else:
        # Manager sees users in their shop(s)
        shop_ids = current.get_shop_ids()
        seen = {current.id}
        users = [current]
        for shop in current.shops.all():
            for u in shop.users.all():
                if u.id not in seen:
                    seen.add(u.id)
                    users.append(u)
    return jsonify({'users': [u.to_dict() for u in users]}), 200


@users_bp.route('/', methods=['POST'])
@manager_required
def create_user():
    current = get_current_user()
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

    role = data['role']
    # Normalise
    if role == 'salesperson':
        role = 'seller'
    # Manager can only create seller; super_admin can create any role
    if current.is_manager and role not in ('seller', 'salesperson'):
        return jsonify({'error': 'Managers can only create Seller accounts'}), 403
    if role not in ('super_admin', 'manager', 'seller'):
        return jsonify({'error': 'Invalid role'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 409

    user = User(
        username=username,
        role=role,
        full_name=data.get('full_name', ''),
    )
    user.set_password(password)
    db.session.add(user)

    # Auto-assign to shop(s)
    shop_ids = data.get('shop_ids') or []
    if not shop_ids and not current.is_super_admin:
        shop_ids = current.get_shop_ids()
    for sid in shop_ids:
        shop = Shop.query.get(sid)
        if shop and (current.is_super_admin or sid in current.get_shop_ids()):
            user.shops.append(shop)

    db.session.commit()
    return jsonify({'user': user.to_dict()}), 201


@users_bp.route('/<int:user_id>', methods=['PUT'])
@manager_required
def update_user(user_id):
    current = get_current_user()
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    if 'full_name' in data:
        user.full_name = data['full_name']
    if 'role' in data:
        role = data['role']
        if role == 'salesperson':
            role = 'seller'
        if current.is_super_admin and role in ('super_admin', 'manager', 'seller'):
            user.role = role
        elif current.is_manager and role in ('seller',):
            user.role = role
    if 'is_active' in data:
        user.is_active = bool(data['is_active'])
    if 'password' in data and data['password']:
        if len(data['password']) < 6:
            return jsonify({'error': 'password must be at least 6 characters'}), 400
        user.set_password(data['password'])

    db.session.commit()
    return jsonify({'user': user.to_dict()}), 200


@users_bp.route('/<int:user_id>', methods=['DELETE'])
@manager_required
def delete_user(user_id):
    current_id = int(get_jwt_identity())
    if current_id == user_id:
        return jsonify({'error': 'Cannot deactivate yourself'}), 400
    user = User.query.get_or_404(user_id)
    user.is_active = False
    db.session.commit()
    return jsonify({'message': 'User deactivated'}), 200
