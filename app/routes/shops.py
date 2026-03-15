from flask import Blueprint, request, jsonify
from app import db
from app.models.shop import Shop
from app.models.user import User
from app.middleware.auth import super_admin_required, login_required, get_current_user

shops_bp = Blueprint('shops', __name__)


@shops_bp.route('/', methods=['GET'])
@login_required
def list_shops():
    user = get_current_user()
    if user.is_super_admin:
        shops = Shop.query.order_by(Shop.name).all()
    else:
        shops = user.shops.order_by(Shop.name).all()
    return jsonify({'shops': [s.to_dict() for s in shops]}), 200


@shops_bp.route('/<int:shop_id>', methods=['GET'])
@login_required
def get_shop(shop_id):
    user = get_current_user()
    shop = Shop.query.get_or_404(shop_id)
    if not user.is_super_admin and shop_id not in user.get_shop_ids():
        return jsonify({'error': 'Access denied'}), 403
    # Include assigned users
    data = shop.to_dict()
    data['users'] = [u.to_dict() for u in shop.users.all()]
    return jsonify({'shop': data}), 200


@shops_bp.route('/', methods=['POST'])
@super_admin_required
def create_shop():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    shop = Shop(
        name=name,
        location=(data.get('location') or '').strip() or None,
        address=(data.get('address') or '').strip() or None,
    )
    db.session.add(shop)
    db.session.commit()
    return jsonify({'shop': shop.to_dict()}), 201


@shops_bp.route('/<int:shop_id>', methods=['PUT'])
@super_admin_required
def update_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    data = request.get_json()
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'name cannot be empty'}), 400
        shop.name = name
    if 'location' in data:
        shop.location = (data.get('location') or '').strip() or None
    if 'address' in data:
        shop.address = (data.get('address') or '').strip() or None
    if 'is_active' in data:
        shop.is_active = bool(data['is_active'])
    db.session.commit()
    return jsonify({'shop': shop.to_dict()}), 200


@shops_bp.route('/<int:shop_id>/users', methods=['POST'])
@super_admin_required
def assign_user(shop_id):
    """Assign a user to a shop."""
    shop = Shop.query.get_or_404(shop_id)
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id is required'}), 400
    user = User.query.get_or_404(user_id)
    if user.is_super_admin:
        return jsonify({'error': 'Super Admin does not belong to any shop'}), 400
    if shop not in user.shops.all():
        user.shops.append(shop)
        db.session.commit()
    return jsonify({'message': f'{user.username} assigned to {shop.name}'}), 200


@shops_bp.route('/<int:shop_id>/users/<int:user_id>', methods=['DELETE'])
@super_admin_required
def remove_user(shop_id, user_id):
    """Remove a user from a shop."""
    shop = Shop.query.get_or_404(shop_id)
    user = User.query.get_or_404(user_id)
    if shop in user.shops.all():
        user.shops.remove(shop)
        db.session.commit()
    return jsonify({'message': f'{user.username} removed from {shop.name}'}), 200
