from flask import Blueprint, request, jsonify
from datetime import datetime, date
from app import db
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.middleware.auth import manager_required, login_required, get_current_user

stock_bp = Blueprint('stock', __name__)


@stock_bp.route('/in', methods=['POST'])
@manager_required
def stock_in():
    user = get_current_user()
    data = request.get_json()
    required = ['product_id', 'quantity', 'unit_price']
    for field in required:
        if data.get(field) is None:
            return jsonify({'error': f'{field} is required'}), 400

    product = Product.query.get(data['product_id'])
    if not product or not product.is_active:
        return jsonify({'error': 'Product not found'}), 404

    quantity = float(data['quantity'])
    if quantity <= 0:
        return jsonify({'error': 'Quantity must be positive'}), 400

    unit_price = float(data['unit_price'])
    if unit_price <= 0:
        return jsonify({'error': 'unit_price must be greater than zero'}), 400

    # Resolve shop_id
    shop_ids = user.get_shop_ids()
    shop_id = data.get('shop_id')
    if not user.is_super_admin:
        if not shop_ids:
            return jsonify({'error': 'You are not assigned to any shop'}), 403
        shop_id = shop_id if shop_id in shop_ids else shop_ids[0]

    movement_date = date.fromisoformat(data['date']) if data.get('date') else date.today()

    movement = StockMovement(
        shop_id=shop_id,
        product_id=data['product_id'],
        quantity_in=quantity,
        quantity_out=0,
        unit_price=unit_price,
        note=data.get('note', ''),
        movement_type='in',
        created_by=user.id,
        date=movement_date,
    )
    db.session.add(movement)
    db.session.commit()

    return jsonify({
        'message': 'Stock added successfully',
        'movement': movement.to_dict(),
        'new_balance': product.current_stock(shop_id=shop_id),
    }), 201


@stock_bp.route('/adjust', methods=['POST'])
@manager_required
def stock_adjust():
    """Set absolute stock level for a product in a shop.
    Calculates the delta and records a positive/negative adjustment movement."""
    user = get_current_user()
    data = request.get_json()

    for field in ('product_id', 'new_quantity'):
        if data.get(field) is None:
            return jsonify({'error': f'{field} is required'}), 400

    product = Product.query.get(data['product_id'])
    if not product or not product.is_active:
        return jsonify({'error': 'Product not found'}), 404

    new_qty = float(data['new_quantity'])
    if new_qty < 0:
        return jsonify({'error': 'new_quantity cannot be negative'}), 400

    shop_ids = user.get_shop_ids()
    shop_id  = data.get('shop_id')
    if not user.is_super_admin:
        if not shop_ids:
            return jsonify({'error': 'You are not assigned to any shop'}), 403
        shop_id = shop_id if shop_id in shop_ids else shop_ids[0]

    current = product.current_stock(shop_id=shop_id)
    delta   = new_qty - current

    if delta == 0:
        return jsonify({'message': 'No change needed', 'current_stock': current}), 200

    movement = StockMovement(
        shop_id       = shop_id,
        product_id    = data['product_id'],
        quantity_in   = max(delta, 0),
        quantity_out  = max(-delta, 0),
        unit_price    = float(product.unit_price),
        note          = data.get('note', ''),
        movement_type = 'adjustment',
        reason        = (data.get('reason') or '').strip() or 'Manual adjustment',
        created_by    = user.id,
        date          = date.today(),
    )
    db.session.add(movement)
    db.session.commit()

    return jsonify({
        'message':     'Stock adjusted',
        'previous':    current,
        'new_balance': product.current_stock(shop_id=shop_id),
        'delta':       delta,
        'movement':    movement.to_dict(),
    }), 201


@stock_bp.route('/balance', methods=['GET'])
@login_required
def stock_balance():
    user = get_current_user()
    shop_id = request.args.get('shop_id', type=int)

    query = Product.query.filter_by(is_active=True)
    if not user.is_super_admin:
        accessible = user.get_shop_ids()
        if shop_id and shop_id in accessible:
            query = query.filter_by(shop_id=shop_id)
        elif accessible:
            query = query.filter(
                (Product.shop_id.in_(accessible)) | (Product.shop_id.is_(None))
            )
        active_shop_id = shop_id if (shop_id and shop_id in accessible) else (accessible[0] if accessible else None)
    else:
        active_shop_id = shop_id

    products = query.order_by(Product.name).all()
    balances = []
    for p in products:
        stock = p.current_stock(shop_id=active_shop_id)
        balances.append({
            'product_id': p.id,
            'shop_id': p.shop_id,
            'product_name': p.name,
            'unit_price': float(p.unit_price),
            'unit': p.unit,
            'current_stock': stock,
            'stock_value': stock * float(p.unit_price),
        })
    return jsonify({'balances': balances}), 200


@stock_bp.route('/movements', methods=['GET'])
@login_required
def stock_movements():
    user = get_current_user()
    product_id = request.args.get('product_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    movement_type = request.args.get('type')
    shop_id = request.args.get('shop_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = StockMovement.query

    if not user.is_super_admin:
        accessible = user.get_shop_ids()
        if shop_id and shop_id in accessible:
            query = query.filter_by(shop_id=shop_id)
        elif accessible:
            query = query.filter(StockMovement.shop_id.in_(accessible))

    if product_id:
        query = query.filter_by(product_id=product_id)
    if movement_type:
        query = query.filter_by(movement_type=movement_type)
    if start_date:
        query = query.filter(StockMovement.date >= date.fromisoformat(start_date))
    if end_date:
        query = query.filter(StockMovement.date <= date.fromisoformat(end_date))

    pagination = query.order_by(StockMovement.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        'movements': [m.to_dict() for m in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page,
    }), 200
