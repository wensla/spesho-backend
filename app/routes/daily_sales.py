from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from datetime import date
from app import db
from app.models.daily_sale import DailySale
from app.middleware.auth import login_required

daily_sales_bp = Blueprint('daily_sales', __name__)


@daily_sales_bp.route('/', methods=['POST'])
@login_required
def record_sale():
    data = request.get_json()

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

    debt = round(total_amount - cash_paid, 2)

    sale_date = date.fromisoformat(data['date']) if data.get('date') else date.today()
    user_id = int(get_jwt_identity())

    sale = DailySale(
        date=sale_date,
        total_amount=total_amount,
        cash_paid=cash_paid,
        debt=debt,
        note=data.get('note'),
        customer_name=data.get('customer_name'),
        customer_phone=data.get('customer_phone'),
        recorded_by=user_id,
    )
    db.session.add(sale)
    db.session.commit()

    return jsonify({'message': 'Sale recorded successfully', 'sale': sale.to_dict()}), 201


@daily_sales_bp.route('/', methods=['GET'])
@login_required
def list_sales():
    from app.models.user import User
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = DailySale.query
    if user.role == 'salesperson':
        query = query.filter_by(recorded_by=user_id)
    if start_date:
        query = query.filter(DailySale.date >= date.fromisoformat(start_date))
    if end_date:
        query = query.filter(DailySale.date <= date.fromisoformat(end_date))

    sales = query.order_by(DailySale.created_at.desc()).all()
    return jsonify({'sales': [s.to_dict() for s in sales]}), 200


@daily_sales_bp.route('/<int:sale_id>', methods=['DELETE'])
@login_required
def delete_sale(sale_id):
    from app.models.user import User
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    sale = DailySale.query.get_or_404(sale_id)
    if user.role == 'salesperson' and sale.recorded_by != user_id:
        return jsonify({'error': 'Unauthorized'}), 403

    db.session.delete(sale)
    db.session.commit()
    return jsonify({'message': 'Sale deleted'}), 200
