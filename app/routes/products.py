from flask import Blueprint, request, jsonify
from app import db
from app.models.product import Product
from app.middleware.auth import manager_required, login_required, get_current_user

products_bp = Blueprint('products', __name__)

_UNGA_WORDS     = ['dona', 'sembe', 'ngano', 'mtama', 'muhogo', 'unga']
_MCHELE_WORDS   = ['mchele']
_MAHARAGE_WORDS = ['maharage']

def _check_category_name(name, category):
    n = name.lower()
    has_unga     = any(w in n for w in _UNGA_WORDS)
    has_mchele   = any(w in n for w in _MCHELE_WORDS)
    has_maharage = any(w in n for w in _MAHARAGE_WORDS)
    if category == 'unga'     and (has_mchele or has_maharage): return 'Sii jamii ya hapa'
    if category == 'mchele'   and (has_unga   or has_maharage): return 'Sii jamii ya hapa'
    if category == 'maharage' and (has_unga   or has_mchele):   return 'Sii jamii ya hapa'
    return None


@products_bp.route('/', methods=['GET'])
@login_required
def list_products():
    user = get_current_user()
    include_stock = request.args.get('include_stock', 'false').lower() == 'true'
    shop_id = request.args.get('shop_id', type=int)

    query = Product.query.filter_by(is_active=True)

    if not user.is_super_admin:
        accessible = user.get_shop_ids()
        if shop_id and shop_id in accessible:
            query = query.filter_by(shop_id=shop_id)
        elif accessible:
            # Show products from accessible shops AND global products (shop_id IS NULL)
            query = query.filter(
                (Product.shop_id.in_(accessible)) | (Product.shop_id.is_(None))
            )
    elif shop_id:
        query = query.filter_by(shop_id=shop_id)

    products = query.order_by(Product.name).all()
    active_shop_id = shop_id or (user.get_shop_ids()[0] if not user.is_super_admin and user.get_shop_ids() else None)
    return jsonify({'products': [p.to_dict(include_stock=include_stock, shop_id=active_shop_id) for p in products]}), 200


@products_bp.route('/<int:product_id>', methods=['GET'])
@login_required
def get_product(product_id):
    user = get_current_user()
    product = Product.query.get_or_404(product_id)
    shop_id = product.shop_id or (user.get_shop_ids()[0] if user.get_shop_ids() else None)
    return jsonify({'product': product.to_dict(include_stock=True, shop_id=shop_id)}), 200


@products_bp.route('/', methods=['POST'])
@manager_required
def create_product():
    user = get_current_user()
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

    category = (data.get('category') or 'unga').strip()
    if category not in ('unga', 'mchele', 'maharage'):
        category = 'unga'
    cat_err = _check_category_name(name, category)
    if cat_err:
        return jsonify({'error': cat_err}), 400

    # Determine shop_id
    shop_id = data.get('shop_id')
    if not user.is_super_admin:
        shop_ids = user.get_shop_ids()
        if not shop_ids:
            return jsonify({'error': 'You are not assigned to any shop'}), 403
        shop_id = shop_id if shop_id in shop_ids else shop_ids[0]

    existing = Product.query.filter_by(name=name, shop_id=shop_id).first()
    if existing and existing.is_active:
        return jsonify({'error': 'Product name already exists'}), 409
    if existing and not existing.is_active:
        existing.unit_price = unit_price
        existing.is_active = True
        if data.get('buying_price') is not None:
            try:
                bp = float(data['buying_price'])
                existing.buying_price = bp if bp >= 0 else None
            except (TypeError, ValueError):
                pass
        package_size = data.get('package_size', 5)
        if package_size in (5, 10, 25):
            existing.package_size = package_size
        db.session.commit()
        return jsonify({'product': existing.to_dict()}), 201

    unit = (data.get('unit') or 'kg').strip()
    if category in ('mchele', 'maharage'):
        package_size = 1
    else:
        package_size = data.get('package_size', 5)
        if package_size not in (5, 10, 25):
            package_size = 5
    buying_price = None
    if data.get('buying_price') is not None:
        try:
            buying_price = float(data['buying_price'])
            if buying_price < 0:
                buying_price = None
        except (TypeError, ValueError):
            pass

    product = Product(shop_id=shop_id, name=name, unit_price=unit_price,
                      buying_price=buying_price, unit=unit,
                      package_size=package_size, category=category)
    db.session.add(product)
    db.session.commit()
    return jsonify({'product': product.to_dict()}), 201


@products_bp.route('/<int:product_id>', methods=['PUT'])
@manager_required
def update_product(product_id):
    user = get_current_user()
    product = Product.query.get_or_404(product_id)

    if not user.is_super_admin and product.shop_id not in user.get_shop_ids():
        return jsonify({'error': 'Access denied'}), 403

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
            check_name = data.get('name', product.name).strip()
            cat_err = _check_category_name(check_name, category)
            if cat_err:
                return jsonify({'error': cat_err}), 400
            product.category = category
            if category in ('mchele', 'maharage'):
                product.package_size = 1
    if 'buying_price' in data:
        try:
            bp = float(data['buying_price'])
            product.buying_price = bp if bp >= 0 else None
        except (TypeError, ValueError):
            pass
    if 'package_size' in data and product.category == 'unga':
        package_size = data.get('package_size')
        if package_size in (5, 10, 25):
            product.package_size = package_size
    if 'name' in data:
        conflict = Product.query.filter(
            Product.name == product.name,
            Product.shop_id == product.shop_id,
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
    user = get_current_user()
    product = Product.query.get_or_404(product_id)
    if not user.is_super_admin and product.shop_id not in user.get_shop_ids():
        return jsonify({'error': 'Access denied'}), 403
    product.is_active = False
    db.session.commit()
    return jsonify({'message': 'Product deleted'}), 200
