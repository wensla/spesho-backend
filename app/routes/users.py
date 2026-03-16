from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from app import db
from app.models.user import User
from app.models.shop import Shop
from app.middleware.auth import manager_required, super_admin_required, get_current_user

users_bp = Blueprint('users', __name__)


# ── GET /api/users/ ──────────────────────────────────────────────────────────
# SRS 3.1: Super Admin sees Managers only
# SRS 3.2: Manager sees their Sellers only
@users_bp.route('/', methods=['GET'])
@manager_required
def list_users():
    current = get_current_user()
    if current.is_super_admin:
        users = User.query.filter_by(role='manager').order_by(User.full_name).all()
    else:
        # Manager sees sellers they registered (manager_id FK)
        users = (
            User.query
            .filter(User.role.in_(['seller', 'salesperson']))
            .filter_by(manager_id=current.id)
            .order_by(User.full_name)
            .all()
        )
    return jsonify({'users': [u.to_dict() for u in users]}), 200


# ── POST /api/users/ ─────────────────────────────────────────────────────────
# SRS 3.1: Super Admin registers Managers
# SRS 3.2: Manager registers Sellers
@users_bp.route('/', methods=['POST'])
@manager_required
def create_user():
    current = get_current_user()
    data = request.get_json()

    for field in ('username', 'password', 'role'):
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    username = data['username'].strip()
    if len(username) < 3:
        return jsonify({'error': 'username must be at least 3 characters'}), 400
    if len(data['password']) < 6:
        return jsonify({'error': 'password must be at least 6 characters'}), 400

    role = data['role']
    if role == 'salesperson':
        role = 'seller'

    # Enforce SRS role rules
    if current.is_super_admin and role != 'manager':
        return jsonify({'error': 'Super Admin can only register Manager accounts'}), 403
    if current.is_manager and role != 'seller':
        return jsonify({'error': 'Managers can only register Seller accounts'}), 403

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 409

    gender = data.get('gender')
    if gender not in ('male', 'female', None):
        gender = None

    user = User(
        username=username,
        role=role,
        full_name=data.get('full_name', ''),
        gender=gender,
        manager_id=current.id if current.is_manager else None,
    )
    user.set_password(data['password'])
    db.session.add(user)

    # Auto-assign seller to manager's shops
    if current.is_manager:
        for sid in current.get_shop_ids():
            shop = Shop.query.get(sid)
            if shop:
                user.shops.append(shop)

    db.session.commit()
    return jsonify({'user': user.to_dict()}), 201


# ── PUT /api/users/<id> ───────────────────────────────────────────────────────
@users_bp.route('/<int:user_id>', methods=['PUT'])
@manager_required
def update_user(user_id):
    current = get_current_user()
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    if 'full_name' in data:
        user.full_name = data['full_name']
    if 'gender' in data:
        g = data['gender']
        user.gender = g if g in ('male', 'female') else None
    if 'password' in data and data['password']:
        if len(data['password']) < 6:
            return jsonify({'error': 'password must be at least 6 characters'}), 400
        user.set_password(data['password'])

    db.session.commit()
    return jsonify({'user': user.to_dict()}), 200


# ── POST /api/users/<id>/toggle-active ───────────────────────────────────────
# Super Admin: toggle manager active state
# Manager: toggle their seller active state
@users_bp.route('/<int:user_id>/toggle-active', methods=['POST'])
@manager_required
def toggle_active(user_id):
    current = get_current_user()
    current_id = int(get_jwt_identity())
    if current_id == user_id:
        return jsonify({'error': 'Cannot deactivate yourself'}), 400
    user = User.query.get_or_404(user_id)
    # Manager can only toggle their own sellers
    if current.is_manager and user.manager_id != current.id:
        return jsonify({'error': 'Not your seller'}), 403
    user.is_active = not user.is_active
    db.session.commit()
    status = 'activated' if user.is_active else 'deactivated'
    return jsonify({'message': f'User {status}', 'user': user.to_dict()}), 200


# ── DELETE /api/users/<id> ────────────────────────────────────────────────────
# Super Admin: delete any manager
# Manager: delete their own sellers
@users_bp.route('/<int:user_id>', methods=['DELETE'])
@manager_required
def delete_user(user_id):
    current = get_current_user()
    current_id = int(get_jwt_identity())
    if current_id == user_id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    user = User.query.get_or_404(user_id)
    if current.is_manager and user.manager_id != current.id:
        return jsonify({'error': 'Not your seller'}), 403
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted'}), 200
