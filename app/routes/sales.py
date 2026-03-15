from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from datetime import date
from app import db
from app.models.product import Product
from app.models.sale import Sale
from app.models.stock_movement import StockMovement
from app.middleware.auth import login_required

sales_bp = Blueprint('sales', __name__)


@sales_bp.route('/', methods=['POST'])
@login_required
def record_sale():
    data = request.get_json()
    required = ['product_id', 'quantity', 'price']
    for field in required:
        if data.get(field) is None:
            return jsonify({'error': f'{field} is required'}), 400

    product = Product.query.get(data['product_id'])
    if not product or not product.is_active:
        return jsonify({'error': 'Product not found'}), 404

    quantity = float(data['quantity'])
    try:
        price = float(data['price'])
    except (TypeError, ValueError):
        return jsonify({'error': 'price must be a number'}), 400
    if price <= 0:
        return jsonify({'error': 'price must be greater than zero'}), 400

    try:
        discount = float(data.get('discount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'discount must be a number'}), 400
    if discount < 0:
        return jsonify({'error': 'discount cannot be negative'}), 400

    if quantity <= 0:
        return jsonify({'error': 'Quantity must be positive'}), 400

    # Check stock availability
    current_stock = product.current_stock()
    if current_stock < quantity:
        return jsonify({
            'error': f'Insufficient stock. Available: {current_stock}, Requested: {quantity}'
        }), 400

    total = (quantity * price) - discount

    # paid na debt: kiasi alicholipa na baki yake (madeni)
    try:
        paid = float(data.get('paid', total))
    except (TypeError, ValueError):
        return jsonify({'error': 'paid must be a number'}), 400
    if paid < 0:
        return jsonify({'error': 'paid cannot be negative'}), 400
    if paid > total:
        return jsonify({'error': f'paid ({paid}) cannot exceed total ({total})'}), 400

    debt = round(total - paid, 2)

    sale_date = date.fromisoformat(data['date']) if data.get('date') else date.today()
    user_id = int(get_jwt_identity())

    sale = Sale(
        product_id=data['product_id'],
        quantity=quantity,
        price=price,
        discount=discount,
        total=total,
        paid=paid,
        debt=debt,
        note=data.get('note', ''),
        sold_by=user_id,
        date=sale_date,
    )
    db.session.add(sale)

    # Record stock movement out
    movement = StockMovement(
        product_id=data['product_id'],
        quantity_in=0,
        quantity_out=quantity,
        unit_price=price,
        note=f'Sale #{sale.id}',
        movement_type='out',
        created_by=user_id,
        date=sale_date,
    )
    db.session.add(movement)
    db.session.commit()

    return jsonify({
        'message': 'Sale recorded successfully',
        'sale': sale.to_dict(),
        'new_balance': product.current_stock(),
    }), 201


@sales_bp.route('/', methods=['GET'])
@login_required
def list_sales():
    from flask_jwt_extended import get_jwt_identity
    from app.models.user import User

    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    product_id = request.args.get('product_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = Sale.query

    # Salesperson can only see their own sales
    if user.role == 'salesperson':
        query = query.filter_by(sold_by=user_id)

    if product_id:
        query = query.filter_by(product_id=product_id)
    if start_date:
        query = query.filter(Sale.date >= date.fromisoformat(start_date))
    if end_date:
        query = query.filter(Sale.date <= date.fromisoformat(end_date))

    pagination = query.order_by(Sale.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        'sales': [s.to_dict() for s in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page,
    }), 200


@sales_bp.route('/<int:sale_id>', methods=['GET'])
@login_required
def get_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    return jsonify({'sale': sale.to_dict()}), 200
