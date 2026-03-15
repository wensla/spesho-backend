from flask import Blueprint, jsonify, request
from datetime import date, timedelta
from sqlalchemy import func, extract
from app import db
from app.models.daily_sale import DailySale
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.debt import Debt, DebtPayment
from app.middleware.auth import login_required, get_current_user

dashboard_bp = Blueprint('dashboard', __name__)

MONTHS_SW = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Ago','Sep','Okt','Nov','Des']


def _sale_filter(query, user, shop_id=None):
    if user.is_seller:
        return query.filter(DailySale.recorded_by == user.id)
    accessible = user.get_shop_ids()
    if shop_id and shop_id in accessible:
        return query.filter(DailySale.shop_id == shop_id)
    if accessible:
        return query.filter(DailySale.shop_id.in_(accessible))
    return query


def _stock_filter(query, user, shop_id=None):
    if user.is_super_admin:
        if shop_id:
            return query.filter(StockMovement.shop_id == shop_id)
        return query
    accessible = user.get_shop_ids()
    if shop_id and shop_id in accessible:
        return query.filter(StockMovement.shop_id == shop_id)
    if accessible:
        return query.filter(StockMovement.shop_id.in_(accessible))
    return query


@dashboard_bp.route('/', methods=['GET'])
@login_required
def dashboard():
    user = get_current_user()
    shop_id = request.args.get('shop_id', type=int)

    today      = date.today()
    month      = today.month
    year       = today.year
    week_start = today - timedelta(days=today.weekday())

    def sale_q():
        return _sale_filter(db.session.query(DailySale), user, shop_id)

    today_sales = sale_q().filter(DailySale.date == today).with_entities(
        func.coalesce(func.sum(DailySale.total_amount), 0)).scalar()

    week_sales = sale_q().filter(DailySale.date >= week_start, DailySale.date <= today).with_entities(
        func.coalesce(func.sum(DailySale.total_amount), 0)).scalar()

    month_sales = sale_q().filter(
        extract('month', DailySale.date) == month,
        extract('year', DailySale.date) == year,
    ).with_entities(func.coalesce(func.sum(DailySale.total_amount), 0)).scalar()

    year_sales = sale_q().filter(
        extract('year', DailySale.date) == year
    ).with_entities(func.coalesce(func.sum(DailySale.total_amount), 0)).scalar()

    month_debts = sale_q().filter(
        extract('month', DailySale.date) == month,
        extract('year', DailySale.date) == year,
    ).with_entities(func.coalesce(func.sum(DailySale.debt), 0)).scalar()

    # Debts
    total_outstanding = db.session.query(
        func.coalesce(func.sum(Debt.total_amount - Debt.amount_paid), 0)
    ).filter(Debt.status != 'paid').scalar()

    total_debtors = db.session.query(func.count(Debt.id)).filter(Debt.status != 'paid').scalar()

    debt_collected_today = db.session.query(
        func.coalesce(func.sum(DebtPayment.amount), 0)
    ).filter(DebtPayment.payment_date == today).scalar()

    # Stock
    prod_query = Product.query.filter_by(is_active=True)
    if not user.is_super_admin:
        accessible = user.get_shop_ids()
        if shop_id and shop_id in accessible:
            prod_query = prod_query.filter_by(shop_id=shop_id)
        elif accessible:
            prod_query = prod_query.filter(
                (Product.shop_id.in_(accessible)) | (Product.shop_id.is_(None))
            )
    products = prod_query.all()
    active_shop = shop_id or (user.get_shop_ids()[0] if not user.is_super_admin and user.get_shop_ids() else None)
    total_stock_kg = sum(p.current_stock(shop_id=active_shop) for p in products)
    total_stock_value = sum(p.current_stock(shop_id=active_shop) * float(p.unit_price) for p in products)

    stock_levels = [
        {'product': p.name, 'stock': p.current_stock(shop_id=active_shop),
         'value': p.current_stock(shop_id=active_shop) * float(p.unit_price)}
        for p in products
    ]

    # Sales graph current month daily
    daily_rows = sale_q().filter(
        extract('month', DailySale.date) == month,
        extract('year', DailySale.date) == year,
    ).with_entities(
        DailySale.date,
        func.sum(DailySale.total_amount).label('total'),
        func.count(DailySale.id).label('count'),
    ).group_by(DailySale.date).order_by(DailySale.date).all()

    sales_graph = [{'date': r.date.isoformat(), 'total': float(r.total), 'count': r.count} for r in daily_rows]

    # Sales last 7 days
    seven_ago = today - timedelta(days=6)
    daily_7d_rows = sale_q().filter(
        DailySale.date >= seven_ago, DailySale.date <= today
    ).with_entities(
        DailySale.date,
        func.coalesce(func.sum(DailySale.total_amount), 0).label('total'),
    ).group_by(DailySale.date).order_by(DailySale.date).all()

    daily_map = {r.date: float(r.total) for r in daily_7d_rows}
    labels_sw = ['Jt','Jn','Jt','Al','Ij','Jm','Jp']
    sales_daily_7d = [
        {'label': labels_sw[(today - timedelta(days=i)).weekday()],
         'date': (today - timedelta(days=i)).isoformat(),
         'total': daily_map.get(today - timedelta(days=i), 0.0)}
        for i in range(6, -1, -1)
    ]

    # Weekly last 6 weeks
    sales_weekly = []
    for i in range(5, -1, -1):
        ws = today - timedelta(days=today.weekday()) - timedelta(weeks=i)
        we = ws + timedelta(days=6)
        total = sale_q().filter(DailySale.date >= ws, DailySale.date <= we).with_entities(
            func.coalesce(func.sum(DailySale.total_amount), 0)).scalar()
        sales_weekly.append({'label': f'W{6-i}', 'week_start': ws.isoformat(), 'total': float(total)})

    # Monthly last 6 months
    sales_monthly = []
    for i in range(5, -1, -1):
        m_offset = today.month - i
        m_val = m_offset if m_offset > 0 else m_offset + 12
        y_val = today.year if m_offset > 0 else today.year - 1
        total = sale_q().filter(
            extract('month', DailySale.date) == m_val,
            extract('year', DailySale.date) == y_val,
        ).with_entities(func.coalesce(func.sum(DailySale.total_amount), 0)).scalar()
        sales_monthly.append({'label': MONTHS_SW[m_val - 1], 'total': float(total)})

    # Stock trend last 30 days
    thirty_ago = today - timedelta(days=29)
    trend_q = _stock_filter(db.session.query(StockMovement), user, shop_id)
    trend_rows = trend_q.filter(
        StockMovement.date >= thirty_ago, StockMovement.date <= today,
    ).with_entities(
        StockMovement.date,
        func.coalesce(func.sum(StockMovement.quantity_in), 0).label('qty_in'),
        func.coalesce(func.sum(StockMovement.quantity_out), 0).label('qty_out'),
    ).group_by(StockMovement.date).order_by(StockMovement.date).all()

    stock_trend = [
        {'date': r.date.isoformat(), 'qty_in': float(r.qty_in), 'qty_out': float(r.qty_out)}
        for r in trend_rows
    ]

    return jsonify({
        'total_sales_today':          float(today_sales),
        'total_sales_week':           float(week_sales),
        'total_sales_month':          float(month_sales),
        'total_sales_year':           float(year_sales),
        'total_discounts_month':      float(month_debts),
        'total_outstanding':          float(total_outstanding),
        'total_debtors':              int(total_debtors),
        'total_debt_collected_today': float(debt_collected_today),
        'total_stock_kg':             total_stock_kg,
        'total_stock_value':          total_stock_value,
        'sales_graph':                sales_graph,
        'stock_levels':               stock_levels,
        'sales_daily_7d':             sales_daily_7d,
        'sales_weekly':               sales_weekly,
        'sales_monthly':              sales_monthly,
        'stock_trend':                stock_trend,
    }), 200
