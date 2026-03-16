from flask import Blueprint, jsonify, request
from datetime import date, timedelta, datetime
from sqlalchemy import func, extract
from app import db
from app.models.debt import Debt, DebtPayment
from app.middleware.auth import login_required, manager_required, get_current_user

debts_bp = Blueprint('debts', __name__)


def _debt_filter(query, user, shop_id=None):
    """Scope debt queries to what the current user can see."""
    if user.is_super_admin:
        if shop_id:
            return query.filter(Debt.shop_id == shop_id)
        return query
    if user.is_seller:
        return query.filter(Debt.seller_id == user.id)
    # Manager — see debts for their shops
    accessible = user.get_shop_ids()
    if shop_id and shop_id in accessible:
        return query.filter(Debt.shop_id == shop_id)
    if accessible:
        return query.filter(Debt.shop_id.in_(accessible))
    return query.filter(Debt.id == -1)  # no shops → empty


def _payment_filter(query, user, shop_id=None):
    """Scope DebtPayment queries via debt's shop_id."""
    if user.is_super_admin:
        if shop_id:
            return query.join(Debt).filter(Debt.shop_id == shop_id)
        return query
    if user.is_seller:
        return query.join(Debt).filter(Debt.seller_id == user.id)
    accessible = user.get_shop_ids()
    if shop_id and shop_id in accessible:
        return query.join(Debt).filter(Debt.shop_id == shop_id)
    if accessible:
        return query.join(Debt).filter(Debt.shop_id.in_(accessible))
    return query.filter(DebtPayment.id == -1)


# ── List debts ────────────────────────────────────────────────────────────────
@debts_bp.route('/', methods=['GET'])
@login_required
def list_debts():
    user     = get_current_user()
    shop_id  = request.args.get('shop_id', type=int)
    status   = request.args.get('status')
    customer = request.args.get('customer')
    q = _debt_filter(Debt.query, user, shop_id)
    if status:
        q = q.filter(Debt.status == status)
    if customer:
        q = q.filter(Debt.customer_name.ilike(f'%{customer}%'))
    debts = q.order_by(Debt.date.desc()).all()
    return jsonify({'debts': [d.to_dict() for d in debts]}), 200


# ── Summary ───────────────────────────────────────────────────────────────────
@debts_bp.route('/summary', methods=['GET'])
@login_required
def summary():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)

    def dq():
        return _debt_filter(db.session.query(Debt), user, shop_id)

    total   = dq().count()
    pending = dq().filter(Debt.status == 'pending').count()
    partial = dq().filter(Debt.status == 'partial').count()
    paid    = dq().filter(Debt.status == 'paid').count()

    total_amount  = dq().with_entities(func.coalesce(func.sum(Debt.total_amount), 0)).scalar()
    total_paid_v  = dq().with_entities(func.coalesce(func.sum(Debt.amount_paid), 0)).scalar()
    total_balance = dq().filter(Debt.status != 'paid').with_entities(
        func.coalesce(func.sum(Debt.total_amount - Debt.amount_paid), 0)
    ).scalar()

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
@login_required
def reports():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    today   = date.today()

    def dq():
        return _debt_filter(db.session.query(Debt), user, shop_id)

    # Daily — last 30 days
    thirty_ago = today - timedelta(days=30)
    daily_rows = dq().filter(Debt.date >= thirty_ago).with_entities(
        Debt.date,
        func.count(Debt.id).label('count'),
        func.coalesce(func.sum(Debt.total_amount), 0).label('total_amount'),
    ).group_by(Debt.date).order_by(Debt.date).all()

    # Monthly — all time grouped by year+month
    monthly_rows = dq().with_entities(
        extract('year',  Debt.date).label('year'),
        extract('month', Debt.date).label('month'),
        func.count(Debt.id).label('count'),
        func.coalesce(func.sum(Debt.total_amount), 0).label('total_amount'),
    ).group_by('year', 'month').order_by('year', 'month').all()

    # Yearly
    yearly_rows = dq().with_entities(
        extract('year', Debt.date).label('year'),
        func.count(Debt.id).label('count'),
        func.coalesce(func.sum(Debt.total_amount), 0).label('total_amount'),
    ).group_by('year').order_by('year').all()

    # Chronic debtors — outstanding ≥ 30 days, not paid
    chronic = dq().filter(
        Debt.status != 'paid',
        Debt.date <= today - timedelta(days=30)
    ).order_by(Debt.date.asc()).all()

    # Today's summary
    today_new       = dq().filter(Debt.date == today).count()
    today_collected = _payment_filter(db.session.query(DebtPayment), user, shop_id).with_entities(
        func.coalesce(func.sum(DebtPayment.amount), 0)
    ).filter(DebtPayment.payment_date == today).scalar()

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
@login_required
def get_debt(debt_id):
    user = get_current_user()
    debt = _debt_filter(Debt.query, user).filter_by(id=debt_id).first_or_404()
    payments = DebtPayment.query.filter_by(debt_id=debt_id)\
        .order_by(DebtPayment.payment_date.desc()).all()
    return jsonify({
        'debt':     debt.to_dict(),
        'payments': [p.to_dict() for p in payments],
    }), 200


# ── Create debt ───────────────────────────────────────────────────────────────
@debts_bp.route('/', methods=['POST'])
@login_required
def create_debt():
    user = get_current_user()
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

    # Resolve shop_id: use provided or first accessible shop
    shop_id = data.get('shop_id')
    if not shop_id:
        ids = user.get_shop_ids()
        shop_id = ids[0] if ids else None

    debt = Debt(
        shop_id        = shop_id,
        seller_id      = user.id,
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
@login_required
def create_debt_from_sale():
    user          = get_current_user()
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

    shop_id = data.get('shop_id')
    if not shop_id:
        ids = user.get_shop_ids()
        shop_id = ids[0] if ids else None

    debt = Debt(
        shop_id        = shop_id,
        seller_id      = user.id,
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
@login_required
def record_payment(debt_id):
    user   = get_current_user()
    debt   = _debt_filter(Debt.query, user).filter_by(id=debt_id).first_or_404()
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
