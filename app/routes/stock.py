from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from datetime import datetime, date
from app import db
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.middleware.auth import manager_required, login_required
from sqlalchemy import func

stock_bp = Blueprint('stock', __name__)


@stock_bp.route('/in', methods=['POST'])
@manager_required
def stock_in():
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

    movement_date = date.fromisoformat(data['date']) if data.get('date') else date.today()
    user_id = int(get_jwt_identity())

    movement = StockMovement(
        product_id=data['product_id'],
        quantity_in=quantity,
        quantity_out=0,
        unit_price=unit_price,
        note=data.get('note', ''),
        movement_type='in',
        created_by=user_id,
        date=movement_date,
    )
    db.session.add(movement)
    db.session.commit()

    return jsonify({
        'message': 'Stock added successfully',
        'movement': movement.to_dict(),
        'new_balance': product.current_stock(),
    }), 201


@stock_bp.route('/balance', methods=['GET'])
@login_required
def stock_balance():
    from app.models.product import Product as P
    products = P.query.filter_by(is_active=True).order_by(P.name).all()
    balances = []
    for p in products:
        stock = p.current_stock()
        balances.append({
            'product_id': p.id,
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
    product_id = request.args.get('product_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    movement_type = request.args.get('type')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = StockMovement.query

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
