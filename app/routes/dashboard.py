from flask import Blueprint, jsonify
from datetime import date, timedelta
from sqlalchemy import func, extract
from app import db
from app.models.daily_sale import DailySale
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.debt import Debt, DebtPayment
from app.middleware.auth import manager_required

dashboard_bp = Blueprint('dashboard', __name__)

MONTHS_SW = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Ago','Sep','Okt','Nov','Des']


@dashboard_bp.route('/', methods=['GET'])
@manager_required
def dashboard():
    today      = date.today()
    month      = today.month
    year       = today.year
    week_start = today - timedelta(days=today.weekday())

    # ── KPI totals ─────────────────────────────────────────────────────────
    today_sales = db.session.query(
        func.coalesce(func.sum(DailySale.total_amount), 0)
    ).filter(DailySale.date == today).scalar()

    week_sales = db.session.query(
        func.coalesce(func.sum(DailySale.total_amount), 0)
    ).filter(DailySale.date >= week_start, DailySale.date <= today).scalar()

    month_sales = db.session.query(
        func.coalesce(func.sum(DailySale.total_amount), 0)
    ).filter(
        extract('month', DailySale.date) == month,
        extract('year',  DailySale.date) == year,
    ).scalar()

    year_sales = db.session.query(
        func.coalesce(func.sum(DailySale.total_amount), 0)
    ).filter(extract('year', DailySale.date) == year).scalar()

    month_discounts = db.session.query(
        func.coalesce(func.sum(DailySale.debt), 0)
    ).filter(
        extract('month', DailySale.date) == month,
        extract('year',  DailySale.date) == year,
    ).scalar()

    # ── Debts ──────────────────────────────────────────────────────────────
    total_outstanding = db.session.query(
        func.coalesce(func.sum(Debt.total_amount - Debt.amount_paid), 0)
    ).filter(Debt.status != 'paid').scalar()

    total_debtors = db.session.query(
        func.count(Debt.id)
    ).filter(Debt.status != 'paid').scalar()

    debt_collected_today = db.session.query(
        func.coalesce(func.sum(DebtPayment.amount), 0)
    ).filter(DebtPayment.payment_date == today).scalar()

    # ── Stock ──────────────────────────────────────────────────────────────
    products          = Product.query.filter_by(is_active=True).all()
    total_stock_kg    = sum(p.current_stock() for p in products)
    total_stock_value = sum(p.current_stock() * float(p.unit_price) for p in products)

    stock_levels = [
        {'product': p.name, 'stock': p.current_stock(),
         'value': p.current_stock() * float(p.unit_price)}
        for p in products
    ]

    # ── Sales graph: current month daily ───────────────────────────────────
    daily_rows = db.session.query(
        DailySale.date,
        func.sum(DailySale.total_amount).label('total'),
        func.count(DailySale.id).label('count'),
    ).filter(
        extract('month', DailySale.date) == month,
        extract('year',  DailySale.date) == year,
    ).group_by(DailySale.date).order_by(DailySale.date).all()

    sales_graph = [
        {'date': r.date.isoformat(), 'total': float(r.total), 'count': r.count}
        for r in daily_rows
    ]

    # ── Sales bar charts ───────────────────────────────────────────────────

    # 1) Daily last 7 days
    seven_ago = today - timedelta(days=6)
    daily_7d_rows = db.session.query(
        DailySale.date,
        func.coalesce(func.sum(DailySale.total_amount), 0).label('total'),
    ).filter(DailySale.date >= seven_ago, DailySale.date <= today
    ).group_by(DailySale.date).order_by(DailySale.date).all()

    # Build full 7-day list (fill 0 for missing days)
    daily_map = {r.date: float(r.total) for r in daily_7d_rows}
    sales_daily_7d = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        wd = d.weekday()  # 0=Mon
        labels_sw = ['Jt','Jn','Jt','Al','Ij','Jm','Jp']
        sales_daily_7d.append({'label': labels_sw[wd], 'date': d.isoformat(), 'total': daily_map.get(d, 0.0)})

    # 2) Weekly last 6 weeks
    sales_weekly = []
    for i in range(5, -1, -1):
        ws = today - timedelta(days=today.weekday()) - timedelta(weeks=i)
        we = ws + timedelta(days=6)
        total = db.session.query(
            func.coalesce(func.sum(DailySale.total_amount), 0)
        ).filter(DailySale.date >= ws, DailySale.date <= we).scalar()
        sales_weekly.append({'label': f'W{6-i}', 'week_start': ws.isoformat(), 'total': float(total)})

    # 3) Monthly last 6 months
    sales_monthly = []
    for i in range(5, -1, -1):
        # subtract i months
        m_offset = today.month - i
        if m_offset <= 0:
            m_val = m_offset + 12
            y_val = today.year - 1
        else:
            m_val = m_offset
            y_val = today.year
        total = db.session.query(
            func.coalesce(func.sum(DailySale.total_amount), 0)
        ).filter(
            extract('month', DailySale.date) == m_val,
            extract('year',  DailySale.date) == y_val,
        ).scalar()
        sales_monthly.append({'label': MONTHS_SW[m_val - 1], 'total': float(total)})

    # ── Stock trend last 30 days ────────────────────────────────────────────
    thirty_ago = today - timedelta(days=29)
    trend_rows = db.session.query(
        StockMovement.date,
        func.coalesce(func.sum(StockMovement.quantity_in),  0).label('qty_in'),
        func.coalesce(func.sum(StockMovement.quantity_out), 0).label('qty_out'),
    ).filter(
        StockMovement.date >= thirty_ago,
        StockMovement.date <= today,
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
        'total_discounts_month':      float(month_discounts),
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
