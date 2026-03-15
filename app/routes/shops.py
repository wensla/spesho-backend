from flask import Blueprint, request, jsonify
from app import db
from app.models.shop import Shop
from app.models.user import User
from app.middleware.auth import super_admin_required, manager_required, login_required, get_current_user

shops_bp = Blueprint('shops', __name__)


@shops_bp.route('/', methods=['GET'])
@login_required
def list_shops():
    user = get_current_user()
    if user.is_super_admin:
        shops = Shop.query.order_by(Shop.name).all()
    elif user.is_manager:
        shops = Shop.query.filter_by(owner_id=user.id).order_by(Shop.name).all()
    else:
        shops = user.shops.filter_by(is_active=True).order_by(Shop.name).all()
    return jsonify({'shops': [s.to_dict() for s in shops]}), 200


@shops_bp.route('/<int:shop_id>', methods=['GET'])
@login_required
def get_shop(shop_id):
    user = get_current_user()
    shop = Shop.query.get_or_404(shop_id)
    if not user.is_super_admin and shop_id not in user.get_shop_ids():
        return jsonify({'error': 'Access denied'}), 403
    data = shop.to_dict()
    data['users'] = [u.to_dict() for u in shop.users.all()]
    return jsonify({'shop': data}), 200


@shops_bp.route('/', methods=['POST'])
@manager_required
def create_shop():
    """Managers and super_admin can create shops. Managers become owner automatically."""
    user = get_current_user()
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    # Set owner: super_admin can specify owner_id, managers own it themselves
    if user.is_super_admin:
        owner_id = data.get('owner_id')  # optional
    else:
        owner_id = user.id
    shop = Shop(
        name=name,
        location=(data.get('location') or '').strip() or None,
        address=(data.get('address') or '').strip() or None,
        owner_id=owner_id,
    )
    db.session.add(shop)
    db.session.commit()
    return jsonify({'shop': shop.to_dict()}), 201


@shops_bp.route('/<int:shop_id>', methods=['PUT'])
@manager_required
def update_shop(shop_id):
    user = get_current_user()
    shop = Shop.query.get_or_404(shop_id)
    # Only owner or super_admin can update
    if not user.is_super_admin and shop.owner_id != user.id:
        return jsonify({'error': 'Access denied'}), 403
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
    if 'is_active' in data and user.is_super_admin:
        shop.is_active = bool(data['is_active'])
    db.session.commit()
    return jsonify({'shop': shop.to_dict()}), 200


@shops_bp.route('/<int:shop_id>/users', methods=['POST'])
@manager_required
def assign_user(shop_id):
    """Assign a seller to a shop. Manager can only assign to their own shops."""
    user = get_current_user()
    shop = Shop.query.get_or_404(shop_id)
    if not user.is_super_admin and shop.owner_id != user.id:
        return jsonify({'error': 'Access denied'}), 403
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id is required'}), 400
    target = User.query.get_or_404(user_id)
    if target.is_super_admin:
        return jsonify({'error': 'Super Admin does not belong to any shop'}), 400
    if shop not in target.shops.all():
        target.shops.append(shop)
        db.session.commit()
    return jsonify({'message': f'{target.username} assigned to {shop.name}'}), 200


@shops_bp.route('/<int:shop_id>/users/<int:user_id>', methods=['DELETE'])
@manager_required
def remove_user(shop_id, user_id):
    user = get_current_user()
    shop = Shop.query.get_or_404(shop_id)
    if not user.is_super_admin and shop.owner_id != user.id:
        return jsonify({'error': 'Access denied'}), 403
    target = User.query.get_or_404(user_id)
    if shop in target.shops.all():
        target.shops.remove(shop)
        db.session.commit()
    return jsonify({'message': f'{target.username} removed from {shop.name}'}), 200
