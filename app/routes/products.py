from flask import Blueprint, request, jsonify
from app import db
from app.models.product import Product
from app.middleware.auth import manager_required, login_required

products_bp = Blueprint('products', __name__)


@products_bp.route('/', methods=['GET'])
@login_required
def list_products():
    include_stock = request.args.get('include_stock', 'false').lower() == 'true'
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    return jsonify({'products': [p.to_dict(include_stock=include_stock) for p in products]}), 200


@products_bp.route('/<int:product_id>', methods=['GET'])
@login_required
def get_product(product_id):
    product = Product.query.get_or_404(product_id)
    return jsonify({'product': product.to_dict(include_stock=True)}), 200


@products_bp.route('/', methods=['POST'])
@manager_required
def create_product():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    if data.get('unit_price') is None:
        return jsonify({'error': 'unit_price is required'}), 400
    try:
        unit_price = float(data['unit_price'])
    except (TypeError, ValueError):
        return jsonify({'error': 'unit_price must be a number'}), 400
    if unit_price <= 0:
        return jsonify({'error': 'unit_price must be greater than zero'}), 400

    existing = Product.query.filter_by(name=name).first()
    if existing and existing.is_active:
        return jsonify({'error': 'Product name already exists'}), 409
    if existing and not existing.is_active:
        # Reactivate deleted product with new values
        existing.unit_price = unit_price
        existing.is_active = True
        package_size = data.get('package_size', 5)
        if package_size in (5, 10, 25):
            existing.package_size = package_size
        db.session.commit()
        return jsonify({'product': existing.to_dict()}), 201

    unit = (data.get('unit') or 'kg').strip()
    category = (data.get('category') or 'unga').strip()
    if category not in ('unga', 'mchele', 'maharage'):
        category = 'unga'
    # mchele and maharage are always 1kg
    if category in ('mchele', 'maharage'):
        package_size = 1
    else:
        package_size = data.get('package_size', 5)
        if package_size not in (5, 10, 25):
            package_size = 5
    product = Product(name=name, unit_price=unit_price, unit=unit, package_size=package_size, category=category)
    db.session.add(product)
    db.session.commit()
    return jsonify({'product': product.to_dict()}), 201


@products_bp.route('/<int:product_id>', methods=['PUT'])
@manager_required
def update_product(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.get_json()
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'name cannot be empty'}), 400
        product.name = name
    if 'unit_price' in data:
        try:
            unit_price = float(data['unit_price'])
        except (TypeError, ValueError):
            return jsonify({'error': 'unit_price must be a number'}), 400
        if unit_price <= 0:
            return jsonify({'error': 'unit_price must be greater than zero'}), 400
        product.unit_price = unit_price
    if 'unit' in data:
        unit = (data.get('unit') or 'kg').strip()
        if unit:
            product.unit = unit
    if 'category' in data:
        category = (data.get('category') or 'unga').strip()
        if category in ('unga', 'mchele', 'maharage'):
            product.category = category
            if category in ('mchele', 'maharage'):
                product.package_size = 1
    if 'package_size' in data and product.category == 'unga':
        package_size = data.get('package_size')
        if package_size in (5, 10, 25):
            product.package_size = package_size
    # Check name uniqueness (exclude self)
    if 'name' in data:
        conflict = Product.query.filter(
            Product.name == product.name,
            Product.id != product_id,
            Product.is_active == True
        ).first()
        if conflict:
            return jsonify({'error': 'Product name already exists'}), 409
    db.session.commit()
    return jsonify({'product': product.to_dict()}), 200


@products_bp.route('/<int:product_id>', methods=['DELETE'])
@manager_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = False
    db.session.commit()
    return jsonify({'message': 'Product deleted'}), 200
