from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from datetime import date
from app import db
from app.models.daily_sale import DailySale, PAYMENT_METHODS
from app.middleware.auth import login_required, get_current_user

daily_sales_bp = Blueprint('daily_sales', __name__)


def _resolve_shop_id(user, requested_shop_id=None):
    """Return the shop_id to use for the current user's operation."""
    shop_ids = user.get_shop_ids()
    if requested_shop_id and requested_shop_id in shop_ids:
        return requested_shop_id
    return shop_ids[0] if shop_ids else None


@daily_sales_bp.route('/', methods=['POST'])
@login_required
def record_sale():
    data = request.get_json()
    user = get_current_user()

    try:
        total_amount = float(data.get('total_amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'total_amount must be a number'}), 400
    if total_amount <= 0:
        return jsonify({'error': 'total_amount must be greater than zero'}), 400

    try:
        cash_paid = float(data.get('cash_paid', total_amount))
    except (TypeError, ValueError):
        return jsonify({'error': 'cash_paid must be a number'}), 400
    if cash_paid < 0:
        return jsonify({'error': 'cash_paid cannot be negative'}), 400
    if cash_paid > total_amount:
        return jsonify({'error': 'cash_paid cannot exceed total_amount'}), 400

    payment_method = data.get('payment_method', 'cash')
    if payment_method not in PAYMENT_METHODS:
        payment_method = 'cash'

    debt = round(total_amount - cash_paid, 2)
    sale_date = date.fromisoformat(data['date']) if data.get('date') else date.today()

    shop_id = _resolve_shop_id(user, data.get('shop_id'))

    sale = DailySale(
        shop_id=shop_id,
        date=sale_date,
        total_amount=total_amount,
        cash_paid=cash_paid,
        debt=debt,
        payment_method=payment_method,
        note=data.get('note'),
        customer_name=data.get('customer_name'),
        customer_phone=data.get('customer_phone'),
        recorded_by=user.id,
    )
    db.session.add(sale)
    db.session.commit()

    return jsonify({'message': 'Sale recorded successfully', 'sale': sale.to_dict()}), 201


@daily_sales_bp.route('/', methods=['GET'])
@login_required
def list_sales():
    user = get_current_user()

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    shop_id = request.args.get('shop_id', type=int)

    query = DailySale.query

    # Seller sees only their own sales; manager/super_admin sees all in their shop(s)
    if user.is_seller:
        query = query.filter_by(recorded_by=user.id)
    else:
        # Filter to accessible shops
        accessible = user.get_shop_ids()
        if shop_id and shop_id in accessible:
            query = query.filter_by(shop_id=shop_id)
        elif accessible:
            query = query.filter(DailySale.shop_id.in_(accessible))

    if start_date:
        query = query.filter(DailySale.date >= date.fromisoformat(start_date))
    if end_date:
        query = query.filter(DailySale.date <= date.fromisoformat(end_date))

    sales = query.order_by(DailySale.created_at.desc()).all()
    return jsonify({'sales': [s.to_dict() for s in sales]}), 200


@daily_sales_bp.route('/<int:sale_id>', methods=['DELETE'])
@login_required
def delete_sale(sale_id):
    user = get_current_user()
    sale = DailySale.query.get_or_404(sale_id)

    if user.is_seller and sale.recorded_by != user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    if not user.is_super_admin and sale.shop_id not in user.get_shop_ids():
        return jsonify({'error': 'Access denied'}), 403

    db.session.delete(sale)
    db.session.commit()
    return jsonify({'message': 'Sale deleted'}), 200
