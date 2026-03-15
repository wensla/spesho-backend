from flask import Blueprint, jsonify, request
from datetime import date, timedelta, datetime
from sqlalchemy import func, extract
from app import db
from app.models.debt import Debt, DebtPayment
from app.middleware.auth import manager_required

debts_bp = Blueprint('debts', __name__)


# ── List debts ────────────────────────────────────────────────────────────────
@debts_bp.route('/', methods=['GET'])
@manager_required
def list_debts():
    status   = request.args.get('status')
    customer = request.args.get('customer')
    q = Debt.query
    if status:
        q = q.filter_by(status=status)
    if customer:
        q = q.filter(Debt.customer_name.ilike(f'%{customer}%'))
    debts = q.order_by(Debt.date.desc()).all()
    return jsonify({'debts': [d.to_dict() for d in debts]}), 200


# ── Summary ───────────────────────────────────────────────────────────────────
@debts_bp.route('/summary', methods=['GET'])
@manager_required
def summary():
    total   = Debt.query.count()
    pending = Debt.query.filter_by(status='pending').count()
    partial = Debt.query.filter_by(status='partial').count()
    paid    = Debt.query.filter_by(status='paid').count()

    total_amount  = db.session.query(func.coalesce(func.sum(Debt.total_amount), 0)).scalar()
    total_paid_v  = db.session.query(func.coalesce(func.sum(Debt.amount_paid),  0)).scalar()
    total_balance = db.session.query(
        func.coalesce(func.sum(Debt.total_amount - Debt.amount_paid), 0)
    ).filter(Debt.status != 'paid').scalar()

    return jsonify({
        'total_debts':   total,
        'pending':       pending,
        'partial':       partial,
        'paid':          paid,
        'total_amount':  float(total_amount),
        'total_paid':    float(total_paid_v),
        'total_balance': float(total_balance),
    }), 200


# ── Reports ───────────────────────────────────────────────────────────────────
@debts_bp.route('/reports', methods=['GET'])
@manager_required
def reports():
    today = date.today()

    # Daily — last 30 days
    thirty_ago = today - timedelta(days=30)
    daily_rows = db.session.query(
        Debt.date,
        func.count(Debt.id).label('count'),
        func.coalesce(func.sum(Debt.total_amount), 0).label('total_amount'),
    ).filter(Debt.date >= thirty_ago).group_by(Debt.date).order_by(Debt.date).all()

    # Monthly — all time grouped by year+month
    monthly_rows = db.session.query(
        extract('year',  Debt.date).label('year'),
        extract('month', Debt.date).label('month'),
        func.count(Debt.id).label('count'),
        func.coalesce(func.sum(Debt.total_amount), 0).label('total_amount'),
    ).group_by('year', 'month').order_by('year', 'month').all()

    # Yearly
    yearly_rows = db.session.query(
        extract('year', Debt.date).label('year'),
        func.count(Debt.id).label('count'),
        func.coalesce(func.sum(Debt.total_amount), 0).label('total_amount'),
    ).group_by('year').order_by('year').all()

    # Chronic debtors — outstanding ≥ 30 days, not paid
    chronic = Debt.query.filter(
        Debt.status != 'paid',
        Debt.date <= today - timedelta(days=30)
    ).order_by(Debt.date.asc()).all()

    # Today's summary
    today_new       = Debt.query.filter(Debt.date == today).count()
    today_collected = db.session.query(
        func.coalesce(func.sum(DebtPayment.amount), 0)
    ).filter(DebtPayment.payment_date == today).scalar()

    import calendar
    month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    return jsonify({
        'today': {
            'new_debts':  today_new,
            'collected':  float(today_collected),
        },
        'daily': [
            {'label': r.date.strftime('%d %b'), 'count': r.count,
             'total_amount': float(r.total_amount)} for r in daily_rows
        ],
        'monthly': [
            {'label': f"{month_names[int(r.month)]} {int(r.year)}",
             'count': r.count, 'total_amount': float(r.total_amount)} for r in monthly_rows
        ],
        'yearly': [
            {'label': str(int(r.year)), 'count': r.count,
             'total_amount': float(r.total_amount)} for r in yearly_rows
        ],
        'chronic_debtors': [d.to_dict() for d in chronic],
    }), 200


# ── Single debt ───────────────────────────────────────────────────────────────
@debts_bp.route('/<int:debt_id>', methods=['GET'])
@manager_required
def get_debt(debt_id):
    debt = Debt.query.get_or_404(debt_id)
    payments = DebtPayment.query.filter_by(debt_id=debt_id)\
        .order_by(DebtPayment.payment_date.desc()).all()
    return jsonify({
        'debt':     debt.to_dict(),
        'payments': [p.to_dict() for p in payments],
    }), 200


# ── Create debt ───────────────────────────────────────────────────────────────
@debts_bp.route('/', methods=['POST'])
@manager_required
def create_debt():
    data = request.get_json()
    customer_name = (data.get('customer_name') or '').strip()
    if not customer_name:
        return jsonify({'error': 'Customer name required'}), 400

    qty        = data.get('quantity')
    unit_price = data.get('unit_price')
    total_amt  = data.get('total_amount') or (
        float(qty or 0) * float(unit_price or 0)
    )
    if not total_amt or float(total_amt) <= 0:
        return jsonify({'error': 'Total amount must be > 0'}), 400

    debt_date = date.today()
    if data.get('date'):
        debt_date = datetime.strptime(data['date'], '%Y-%m-%d').date()

    debt = Debt(
        customer_name  = customer_name,
        customer_phone = data.get('customer_phone'),
        product_id     = data.get('product_id'),
        quantity       = qty,
        unit_price     = unit_price,
        total_amount   = float(total_amt),
        amount_paid    = 0,
        note           = data.get('note'),
        date           = debt_date,
        status         = 'pending',
    )
    db.session.add(debt)
    db.session.commit()
    return jsonify({'debt': debt.to_dict()}), 201


# ── Create debt from sale ─────────────────────────────────────────────────────
@debts_bp.route('/from-sale', methods=['POST'])
@manager_required
def create_debt_from_sale():
    data          = request.get_json()
    customer_name = (data.get('customer_name') or '').strip()
    if not customer_name:
        return jsonify({'error': 'Customer name required'}), 400

    total_amount = float(data.get('total_amount', 0))
    amount_paid  = float(data.get('amount_paid', 0))
    if total_amount <= 0:
        return jsonify({'error': 'Total amount must be > 0'}), 400

    balance = total_amount - amount_paid
    status  = 'paid' if balance <= 0 else ('partial' if amount_paid > 0 else 'pending')

    debt_date = date.today()
    if data.get('date'):
        debt_date = datetime.strptime(data['date'], '%Y-%m-%d').date()

    debt = Debt(
        customer_name  = customer_name,
        customer_phone = data.get('customer_phone'),
        total_amount   = total_amount,
        amount_paid    = amount_paid,
        note           = data.get('note'),
        date           = debt_date,
        status         = status,
    )
    db.session.add(debt)
    db.session.commit()
    return jsonify({'debt': debt.to_dict()}), 201


# ── Record payment ────────────────────────────────────────────────────────────
@debts_bp.route('/<int:debt_id>/payments', methods=['POST'])
@manager_required
def record_payment(debt_id):
    debt   = Debt.query.get_or_404(debt_id)
    data   = request.get_json()
    amount = float(data.get('amount', 0))
    if amount <= 0:
        return jsonify({'error': 'Amount must be > 0'}), 400

    pay_date = date.today()
    if data.get('date'):
        pay_date = datetime.strptime(data['date'], '%Y-%m-%d').date()

    payment = DebtPayment(
        debt_id      = debt_id,
        amount       = amount,
        note         = data.get('note'),
        payment_date = pay_date,
    )
    db.session.add(payment)

    debt.amount_paid = float(debt.amount_paid or 0) + amount
    if float(debt.amount_paid) >= float(debt.total_amount):
        debt.status = 'paid'
    elif float(debt.amount_paid) > 0:
        debt.status = 'partial'

    db.session.commit()
    return jsonify({'debt': debt.to_dict(), 'payment': payment.to_dict()}), 201
