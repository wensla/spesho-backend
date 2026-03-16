from flask import Blueprint, request, jsonify, send_file
from datetime import date, timedelta
from sqlalchemy import func, extract
import csv
import io
from app import db
from app.models.daily_sale import DailySale
from app.models.stock_movement import StockMovement
from app.models.product import Product
from app.models.debt import Debt, DebtPayment
from app.middleware.auth import manager_required, login_required, get_current_user
from app.utils.pdf_generator import (
    generate_sales_pdf, generate_stock_pdf, generate_stock_balance_pdf,
    generate_daily_sales_pdf, generate_yearly_report_pdf,
    generate_shop_summary_pdf,
)

reports_bp = Blueprint('reports', __name__)


def _parse_dates():
    start_date = request.args.get('start_date')
    end_date   = request.args.get('end_date')
    sd = date.fromisoformat(start_date) if start_date else None
    ed = date.fromisoformat(end_date)   if end_date   else None
    return sd, ed


def _sale_scope(query, user, shop_id=None):
    """Filter DailySale query to what the user can see."""
    if user.is_seller:
        return query.filter(DailySale.recorded_by == user.id)
    accessible = user.get_shop_ids()
    if shop_id and shop_id in accessible:
        return query.filter(DailySale.shop_id == shop_id)
    if accessible:
        return query.filter(DailySale.shop_id.in_(accessible))
    return query  # super admin → all


def _stock_scope(query, user, shop_id=None):
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


# ── Sales summary (date range) ────────────────────────────────────────────────
@reports_bp.route('/sales-summary', methods=['GET'])
@login_required
def sales_summary():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    sd, ed  = _parse_dates()
    if not sd or not ed:
        return jsonify({'error': 'start_date and end_date required'}), 400

    q = _sale_scope(db.session.query(DailySale), user, shop_id)
    daily_rows = q.filter(
        DailySale.date >= sd, DailySale.date <= ed
    ).with_entities(
        DailySale.date,
        func.sum(DailySale.total_amount).label('total'),
        func.sum(DailySale.cash_paid).label('cash_paid'),
        func.sum(DailySale.debt).label('debt'),
        func.count(DailySale.id).label('entries'),
    ).group_by(DailySale.date).order_by(DailySale.date).all()

    days = [{
        'date':      r.date.isoformat(),
        'total':     float(r.total or 0),
        'cash_paid': float(r.cash_paid or 0),
        'debt':      float(r.debt or 0),
        'entries':   r.entries or 0,
    } for r in daily_rows]

    return jsonify({
        'start_date':  sd.isoformat(),
        'end_date':    ed.isoformat(),
        'days':        days,
        'grand_total': sum(d['total']     for d in days),
        'grand_cash':  sum(d['cash_paid'] for d in days),
        'grand_debt':  sum(d['debt']      for d in days),
    }), 200


# ── Daily ─────────────────────────────────────────────────────────────────────
@reports_bp.route('/daily', methods=['GET'])
@login_required
def daily_report():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    d = date.fromisoformat(request.args.get('date', date.today().isoformat()))

    q = _sale_scope(DailySale.query, user, shop_id).filter(DailySale.date == d)
    sales = q.order_by(DailySale.created_at).all()

    summary = _sale_scope(db.session.query(DailySale), user, shop_id).filter(
        DailySale.date == d
    ).with_entities(
        func.sum(DailySale.total_amount),
        func.sum(DailySale.cash_paid),
        func.sum(DailySale.debt),
        func.count(DailySale.id),
    ).first()

    # Payment method breakdown
    pay_rows = _sale_scope(db.session.query(DailySale), user, shop_id).filter(
        DailySale.date == d
    ).with_entities(
        DailySale.payment_method,
        func.sum(DailySale.total_amount).label('total'),
        func.count(DailySale.id).label('count'),
    ).group_by(DailySale.payment_method).all()

    return jsonify({
        'date':               d.isoformat(),
        'sales':              [s.to_dict() for s in sales],
        'total_revenue':      float(summary[0] or 0),
        'total_cash':         float(summary[1] or 0),
        'total_debt':         float(summary[2] or 0),
        'total_transactions': summary[3] or 0,
        'payment_breakdown':  [
            {'method': r.payment_method, 'total': float(r.total or 0), 'count': r.count}
            for r in pay_rows
        ],
    }), 200


# ── Daily PDF ─────────────────────────────────────────────────────────────────
@reports_bp.route('/daily/pdf', methods=['GET'])
@login_required
def daily_report_pdf():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    d = date.fromisoformat(request.args.get('date', date.today().isoformat()))
    sales = _sale_scope(DailySale.query, user, shop_id).filter(DailySale.date == d).all()
    pdf = generate_daily_sales_pdf(
        [s.to_dict() for s in sales],
        title='Daily Sales Report',
        subtitle=f'Date: {d.isoformat()}',
    )
    return send_file(pdf, mimetype='application/pdf',
                     download_name=f'sales_daily_{d.isoformat()}.pdf')


# ── Daily CSV ─────────────────────────────────────────────────────────────────
@reports_bp.route('/daily/csv', methods=['GET'])
@login_required
def daily_report_csv():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    d = date.fromisoformat(request.args.get('date', date.today().isoformat()))
    sales = _sale_scope(DailySale.query, user, shop_id).filter(DailySale.date == d).all()
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['#', 'Date', 'Customer', 'Total', 'Cash Paid', 'Debt', 'Payment Method', 'Note', 'Recorded By'])
    for i, s in enumerate(sales, 1):
        d_row = s.to_dict()
        w.writerow([i, d_row['date'], d_row.get('customer_name', ''),
                    d_row['total_amount'], d_row['cash_paid'], d_row['debt'],
                    d_row['payment_label'], d_row.get('note', ''), d_row.get('recorded_by_name', '')])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()),
                     mimetype='text/csv', download_name=f'sales_daily_{d.isoformat()}.csv')


# ── Weekly ────────────────────────────────────────────────────────────────────
@reports_bp.route('/weekly', methods=['GET'])
@login_required
def weekly_report():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    ws_str  = request.args.get('week_start')
    if ws_str:
        week_start = date.fromisoformat(ws_str)
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    q_daily = _sale_scope(db.session.query(DailySale), user, shop_id)

    def _sum(extra_filter=None):
        q = q_daily.filter(DailySale.date >= week_start, DailySale.date <= week_end)
        if extra_filter is not None:
            q = q.filter(extra_filter)
        return q.with_entities(
            func.sum(DailySale.total_amount),
            func.sum(DailySale.cash_paid),
            func.sum(DailySale.debt),
            func.count(DailySale.id),
        ).first()

    summary = _sum()

    # Per-day breakdown
    day_rows = q_daily.filter(
        DailySale.date >= week_start, DailySale.date <= week_end
    ).with_entities(
        DailySale.date,
        func.sum(DailySale.total_amount).label('total'),
        func.sum(DailySale.cash_paid).label('cash_paid'),
        func.sum(DailySale.debt).label('debt'),
        func.count(DailySale.id).label('count'),
    ).group_by(DailySale.date).order_by(DailySale.date).all()

    # Payment method breakdown
    pay_rows = q_daily.filter(
        DailySale.date >= week_start, DailySale.date <= week_end
    ).with_entities(
        DailySale.payment_method,
        func.sum(DailySale.total_amount).label('total'),
        func.count(DailySale.id).label('count'),
    ).group_by(DailySale.payment_method).all()

    return jsonify({
        'week_start':         week_start.isoformat(),
        'week_end':           week_end.isoformat(),
        'total_revenue':      float(summary[0] or 0),
        'total_cash':         float(summary[1] or 0),
        'total_debt':         float(summary[2] or 0),
        'total_transactions': summary[3] or 0,
        'daily_breakdown': [{
            'date':      r.date.isoformat(),
            'total':     float(r.total or 0),
            'cash_paid': float(r.cash_paid or 0),
            'debt':      float(r.debt or 0),
            'count':     r.count,
        } for r in day_rows],
        'payment_breakdown': [
            {'method': r.payment_method, 'total': float(r.total or 0), 'count': r.count}
            for r in pay_rows
        ],
    }), 200


# ── Weekly PDF ────────────────────────────────────────────────────────────────
@reports_bp.route('/weekly/pdf', methods=['GET'])
@login_required
def weekly_report_pdf():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    ws_str  = request.args.get('week_start')
    if ws_str:
        week_start = date.fromisoformat(ws_str)
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    sales = _sale_scope(DailySale.query, user, shop_id).filter(
        DailySale.date >= week_start, DailySale.date <= week_end
    ).order_by(DailySale.date).all()
    pdf = generate_daily_sales_pdf(
        [s.to_dict() for s in sales],
        title='Weekly Sales Report',
        subtitle=f'Week: {week_start.isoformat()} to {week_end.isoformat()}',
    )
    return send_file(pdf, mimetype='application/pdf',
                     download_name=f'sales_weekly_{week_start.isoformat()}.pdf')


# ── Weekly CSV ────────────────────────────────────────────────────────────────
@reports_bp.route('/weekly/csv', methods=['GET'])
@login_required
def weekly_report_csv():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    ws_str  = request.args.get('week_start')
    if ws_str:
        week_start = date.fromisoformat(ws_str)
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    sales = _sale_scope(DailySale.query, user, shop_id).filter(
        DailySale.date >= week_start, DailySale.date <= week_end
    ).order_by(DailySale.date).all()
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['#', 'Date', 'Customer', 'Total', 'Cash Paid', 'Debt', 'Payment Method', 'Note', 'Shop'])
    for i, s in enumerate(sales, 1):
        d = s.to_dict()
        w.writerow([i, d['date'], d.get('customer_name', ''),
                    d['total_amount'], d['cash_paid'], d['debt'],
                    d['payment_label'], d.get('note', ''), d.get('shop_name', '')])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()),
                     mimetype='text/csv',
                     download_name=f'sales_weekly_{week_start.isoformat()}.csv')


# ── Monthly ───────────────────────────────────────────────────────────────────
@reports_bp.route('/monthly', methods=['GET'])
@login_required
def monthly_report():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    month   = request.args.get('month', type=int, default=date.today().month)
    year    = request.args.get('year',  type=int, default=date.today().year)

    q = _sale_scope(db.session.query(DailySale), user, shop_id).filter(
        extract('month', DailySale.date) == month,
        extract('year',  DailySale.date) == year,
    )

    summary = q.with_entities(
        func.sum(DailySale.total_amount),
        func.sum(DailySale.cash_paid),
        func.sum(DailySale.debt),
        func.count(DailySale.id),
    ).first()

    # Daily breakdown within month
    day_rows = q.with_entities(
        DailySale.date,
        func.sum(DailySale.total_amount).label('total'),
        func.sum(DailySale.cash_paid).label('cash_paid'),
        func.sum(DailySale.debt).label('debt'),
        func.count(DailySale.id).label('count'),
    ).group_by(DailySale.date).order_by(DailySale.date).all()

    # Payment method breakdown
    pay_rows = q.with_entities(
        DailySale.payment_method,
        func.sum(DailySale.total_amount).label('total'),
        func.count(DailySale.id).label('count'),
    ).group_by(DailySale.payment_method).all()

    return jsonify({
        'month':              month,
        'year':               year,
        'total_revenue':      float(summary[0] or 0),
        'total_cash':         float(summary[1] or 0),
        'total_debt':         float(summary[2] or 0),
        'total_transactions': summary[3] or 0,
        'daily_breakdown': [{
            'date':      r.date.isoformat(),
            'total':     float(r.total or 0),
            'cash_paid': float(r.cash_paid or 0),
            'debt':      float(r.debt or 0),
            'count':     r.count,
        } for r in day_rows],
        'payment_breakdown': [
            {'method': r.payment_method, 'total': float(r.total or 0), 'count': r.count}
            for r in pay_rows
        ],
    }), 200


# ── Monthly PDF ───────────────────────────────────────────────────────────────
@reports_bp.route('/monthly/pdf', methods=['GET'])
@login_required
def monthly_report_pdf():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    month   = request.args.get('month', type=int, default=date.today().month)
    year    = request.args.get('year',  type=int, default=date.today().year)
    sales = _sale_scope(DailySale.query, user, shop_id).filter(
        extract('month', DailySale.date) == month,
        extract('year',  DailySale.date) == year,
    ).order_by(DailySale.date).all()
    pdf = generate_daily_sales_pdf(
        [s.to_dict() for s in sales],
        title='Monthly Sales Report',
        subtitle=f'Month: {year}-{month:02d}',
    )
    return send_file(pdf, mimetype='application/pdf',
                     download_name=f'sales_monthly_{year}_{month:02d}.pdf')


# ── Monthly CSV ───────────────────────────────────────────────────────────────
@reports_bp.route('/monthly/csv', methods=['GET'])
@login_required
def monthly_report_csv():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    month   = request.args.get('month', type=int, default=date.today().month)
    year    = request.args.get('year',  type=int, default=date.today().year)
    sales = _sale_scope(DailySale.query, user, shop_id).filter(
        extract('month', DailySale.date) == month,
        extract('year',  DailySale.date) == year,
    ).order_by(DailySale.date).all()
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['#', 'Date', 'Customer', 'Total', 'Cash Paid', 'Debt', 'Payment Method', 'Note', 'Shop'])
    for i, s in enumerate(sales, 1):
        d = s.to_dict()
        w.writerow([i, d['date'], d.get('customer_name', ''),
                    d['total_amount'], d['cash_paid'], d['debt'],
                    d['payment_label'], d.get('note', ''), d.get('shop_name', '')])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()),
                     mimetype='text/csv',
                     download_name=f'sales_monthly_{year}_{month:02d}.csv')


# ── Yearly ────────────────────────────────────────────────────────────────────
@reports_bp.route('/yearly', methods=['GET'])
@login_required
def yearly_report():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    year    = request.args.get('year', type=int, default=date.today().year)

    q = _sale_scope(db.session.query(DailySale), user, shop_id).filter(
        extract('year', DailySale.date) == year
    )

    summary = q.with_entities(
        func.sum(DailySale.total_amount),
        func.sum(DailySale.cash_paid),
        func.sum(DailySale.debt),
        func.count(DailySale.id),
    ).first()

    # Monthly breakdown
    month_rows = q.with_entities(
        extract('month', DailySale.date).label('month'),
        func.sum(DailySale.total_amount).label('total'),
        func.sum(DailySale.cash_paid).label('cash_paid'),
        func.sum(DailySale.debt).label('debt'),
        func.count(DailySale.id).label('count'),
    ).group_by('month').order_by('month').all()

    # Payment method breakdown
    pay_rows = q.with_entities(
        DailySale.payment_method,
        func.sum(DailySale.total_amount).label('total'),
        func.count(DailySale.id).label('count'),
    ).group_by(DailySale.payment_method).all()

    MONTH_NAMES = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    return jsonify({
        'year':               year,
        'total_revenue':      float(summary[0] or 0),
        'total_cash':         float(summary[1] or 0),
        'total_debt':         float(summary[2] or 0),
        'total_transactions': summary[3] or 0,
        'monthly_breakdown': [{
            'month':     int(r.month),
            'label':     MONTH_NAMES[int(r.month)],
            'total':     float(r.total or 0),
            'cash_paid': float(r.cash_paid or 0),
            'debt':      float(r.debt or 0),
            'count':     r.count,
        } for r in month_rows],
        'payment_breakdown': [
            {'method': r.payment_method, 'total': float(r.total or 0), 'count': r.count}
            for r in pay_rows
        ],
    }), 200


# ── Yearly PDF ────────────────────────────────────────────────────────────────
@reports_bp.route('/yearly/pdf', methods=['GET'])
@login_required
def yearly_report_pdf():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    year    = request.args.get('year', type=int, default=date.today().year)

    MONTH_NAMES = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    q = _sale_scope(db.session.query(DailySale), user, shop_id).filter(
        extract('year', DailySale.date) == year
    )
    month_rows = q.with_entities(
        extract('month', DailySale.date).label('month'),
        func.sum(DailySale.total_amount).label('total'),
        func.sum(DailySale.cash_paid).label('cash_paid'),
        func.sum(DailySale.debt).label('debt'),
        func.count(DailySale.id).label('count'),
    ).group_by('month').order_by('month').all()

    rows = [{
        'month':     MONTH_NAMES[int(r.month)],
        'total':     float(r.total or 0),
        'cash_paid': float(r.cash_paid or 0),
        'debt':      float(r.debt or 0),
        'count':     r.count,
    } for r in month_rows]

    pdf = generate_yearly_report_pdf(rows, year=year)
    return send_file(pdf, mimetype='application/pdf',
                     download_name=f'sales_yearly_{year}.pdf')


# ── Yearly CSV ────────────────────────────────────────────────────────────────
@reports_bp.route('/yearly/csv', methods=['GET'])
@login_required
def yearly_report_csv():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    year    = request.args.get('year', type=int, default=date.today().year)

    MONTH_NAMES = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    q = _sale_scope(db.session.query(DailySale), user, shop_id).filter(
        extract('year', DailySale.date) == year
    )
    month_rows = q.with_entities(
        extract('month', DailySale.date).label('month'),
        func.sum(DailySale.total_amount).label('total'),
        func.sum(DailySale.cash_paid).label('cash_paid'),
        func.sum(DailySale.debt).label('debt'),
        func.count(DailySale.id).label('count'),
    ).group_by('month').order_by('month').all()

    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['Month', 'Total Revenue', 'Cash Paid', 'Debt', 'Transactions'])
    for r in month_rows:
        w.writerow([MONTH_NAMES[int(r.month)],
                    float(r.total or 0), float(r.cash_paid or 0), float(r.debt or 0), r.count])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()),
                     mimetype='text/csv', download_name=f'sales_yearly_{year}.csv')


# ── Stock movement ────────────────────────────────────────────────────────────
@reports_bp.route('/stock-movement', methods=['GET'])
@login_required
def stock_movement_report():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    sd, ed  = _parse_dates()
    q = _stock_scope(StockMovement.query, user, shop_id)
    if sd:
        q = q.filter(StockMovement.date >= sd)
    if ed:
        q = q.filter(StockMovement.date <= ed)
    movements = q.order_by(StockMovement.date.desc()).all()
    return jsonify({'movements': [m.to_dict() for m in movements]}), 200


# ── Stock movement PDF ────────────────────────────────────────────────────────
@reports_bp.route('/stock-movement/pdf', methods=['GET'])
@login_required
def stock_movement_pdf():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    sd, ed  = _parse_dates()
    q = _stock_scope(StockMovement.query, user, shop_id)
    if sd:
        q = q.filter(StockMovement.date >= sd)
    if ed:
        q = q.filter(StockMovement.date <= ed)
    movements = q.order_by(StockMovement.date.desc()).all()
    pdf = generate_stock_pdf(
        [m.to_dict() for m in movements],
        title='Stock Movement Report',
        subtitle=f'{sd or "All"} to {ed or "Today"}',
    )
    return send_file(pdf, mimetype='application/pdf', download_name='stock_movement.pdf')


# ── Stock movement CSV ────────────────────────────────────────────────────────
@reports_bp.route('/stock-movement/csv', methods=['GET'])
@login_required
def stock_movement_csv():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    sd, ed  = _parse_dates()
    q = _stock_scope(StockMovement.query, user, shop_id)
    if sd:
        q = q.filter(StockMovement.date >= sd)
    if ed:
        q = q.filter(StockMovement.date <= ed)
    movements = q.order_by(StockMovement.date.desc()).all()
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['#', 'Date', 'Product', 'In', 'Out', 'Unit Price', 'Type', 'Reason', 'Shop'])
    for i, m in enumerate(movements, 1):
        d = m.to_dict()
        w.writerow([i, d['date'], d['product_name'],
                    d['quantity_in'], d['quantity_out'],
                    d.get('unit_price', ''), d['movement_type'],
                    d.get('reason', ''), d.get('shop_name', '')])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()),
                     mimetype='text/csv', download_name='stock_movement.csv')


# ── Stock balance PDF ─────────────────────────────────────────────────────────
@reports_bp.route('/stock-balance/pdf', methods=['GET'])
@login_required
def stock_balance_pdf():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    if not user.is_super_admin:
        accessible = user.get_shop_ids()
        active_shop = shop_id if shop_id in accessible else (accessible[0] if accessible else None)
        products = Product.query.filter(
            Product.is_active == True,
            (Product.shop_id.in_(accessible)) | (Product.shop_id.is_(None))
        ).order_by(Product.name).all()
    else:
        active_shop = shop_id
        q = Product.query.filter_by(is_active=True)
        if shop_id:
            q = q.filter_by(shop_id=shop_id)
        products = q.order_by(Product.name).all()

    balances = [{
        'product_name':  p.name,
        'unit_price':    float(p.unit_price),
        'buying_price':  float(p.buying_price) if p.buying_price else None,
        'current_stock': p.current_stock(shop_id=active_shop),
        'stock_value':   p.current_stock(shop_id=active_shop) * float(p.unit_price),
    } for p in products]
    pdf = generate_stock_balance_pdf(balances)
    return send_file(pdf, mimetype='application/pdf', download_name='stock_balance.pdf')


# ── Stock balance CSV ─────────────────────────────────────────────────────────
@reports_bp.route('/stock-balance/csv', methods=['GET'])
@login_required
def stock_balance_csv():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    if not user.is_super_admin:
        accessible = user.get_shop_ids()
        active_shop = shop_id if shop_id in accessible else (accessible[0] if accessible else None)
        products = Product.query.filter(
            Product.is_active == True,
            (Product.shop_id.in_(accessible)) | (Product.shop_id.is_(None))
        ).order_by(Product.name).all()
    else:
        active_shop = shop_id
        q = Product.query.filter_by(is_active=True)
        if shop_id:
            q = q.filter_by(shop_id=shop_id)
        products = q.order_by(Product.name).all()

    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['#', 'Product', 'Unit Price', 'Buying Price', 'Current Stock', 'Stock Value'])
    for i, p in enumerate(products, 1):
        stock = p.current_stock(shop_id=active_shop)
        w.writerow([i, p.name, float(p.unit_price),
                    float(p.buying_price) if p.buying_price else '',
                    stock, stock * float(p.unit_price)])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()),
                     mimetype='text/csv', download_name='stock_balance.csv')


# ── Multi-shop combined PDF (managers/super admin) ────────────────────────────
@reports_bp.route('/shop-summary/pdf', methods=['GET'])
@manager_required
def shop_summary_pdf():
    user  = get_current_user()
    month = request.args.get('month', type=int, default=date.today().month)
    year  = request.args.get('year',  type=int, default=date.today().year)

    from app.models.shop import Shop
    if user.is_super_admin:
        shops = Shop.query.filter_by(is_active=True).all()
    else:
        shop_ids = user.get_shop_ids()
        shops    = Shop.query.filter(Shop.id.in_(shop_ids)).all()

    shop_data = []
    for shop in shops:
        q = db.session.query(DailySale).filter(
            DailySale.shop_id == shop.id,
            extract('month', DailySale.date) == month,
            extract('year',  DailySale.date) == year,
        )
        sm = q.with_entities(
            func.sum(DailySale.total_amount),
            func.sum(DailySale.cash_paid),
            func.sum(DailySale.debt),
            func.count(DailySale.id),
        ).first()
        shop_data.append({
            'shop_name':     shop.name,
            'total':         float(sm[0] or 0),
            'cash_paid':     float(sm[1] or 0),
            'debt':          float(sm[2] or 0),
            'transactions':  sm[3] or 0,
        })

    pdf = generate_shop_summary_pdf(shop_data, month=month, year=year)
    return send_file(pdf, mimetype='application/pdf',
                     download_name=f'shop_summary_{year}_{month:02d}.pdf')


# ── Debt reports ──────────────────────────────────────────────────────────────
@reports_bp.route('/debts/pdf', methods=['GET'])
@login_required
def debts_pdf():
    from app.utils.pdf_generator import generate_debts_pdf
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    status  = request.args.get('status')

    from app.routes.debts import _debt_filter
    q = _debt_filter(Debt.query, user, shop_id)
    if status:
        q = q.filter(Debt.status == status)
    debts = q.order_by(Debt.date.desc()).all()
    pdf = generate_debts_pdf([d.to_dict() for d in debts], status=status)
    return send_file(pdf, mimetype='application/pdf', download_name='debts_report.pdf')


@reports_bp.route('/debts/csv', methods=['GET'])
@login_required
def debts_csv():
    user    = get_current_user()
    shop_id = request.args.get('shop_id', type=int)
    status  = request.args.get('status')

    from app.routes.debts import _debt_filter
    q = _debt_filter(Debt.query, user, shop_id)
    if status:
        q = q.filter(Debt.status == status)
    debts = q.order_by(Debt.date.desc()).all()

    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['#', 'Date', 'Customer', 'Phone', 'Product', 'Qty',
                'Total', 'Paid', 'Balance', 'Status', 'Days Outstanding', 'Shop'])
    for i, debt in enumerate(debts, 1):
        d = debt.to_dict()
        w.writerow([i, d['date'], d['customer_name'], d.get('customer_phone', ''),
                    d.get('product_name', ''), d.get('quantity', ''),
                    d['total_amount'], d['amount_paid'], d['balance'],
                    d['status'], d['days_outstanding'], d.get('shop_name', '')])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()),
                     mimetype='text/csv', download_name='debts_report.csv')
