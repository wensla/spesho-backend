from flask import Blueprint, request, jsonify, send_file
from datetime import date, timedelta
from sqlalchemy import func, extract
from app import db
from app.models.sale import Sale
from app.models.stock_movement import StockMovement
from app.models.product import Product
from app.middleware.auth import manager_required, login_required
from app.utils.pdf_generator import generate_sales_pdf, generate_stock_pdf, generate_stock_balance_pdf

reports_bp = Blueprint('reports', __name__)


def _parse_dates():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    sd = date.fromisoformat(start_date) if start_date else None
    ed = date.fromisoformat(end_date) if end_date else None
    return sd, ed


@reports_bp.route('/daily', methods=['GET'])
@manager_required
def daily_report():
    report_date = request.args.get('date', date.today().isoformat())
    d = date.fromisoformat(report_date)

    sales = Sale.query.filter(Sale.date == d).order_by(Sale.created_at).all()
    summary = db.session.query(
        func.sum(Sale.paid),
        func.sum(Sale.discount),
        func.count(Sale.id),
    ).filter(Sale.date == d).first()

    return jsonify({
        'date': d.isoformat(),
        'sales': [s.to_dict() for s in sales],
        'total_revenue': float(summary[0] or 0),
        'total_discounts': float(summary[1] or 0),
        'total_transactions': summary[2] or 0,
    }), 200


@reports_bp.route('/monthly', methods=['GET'])
@manager_required
def monthly_report():
    month = request.args.get('month', type=int, default=date.today().month)
    year = request.args.get('year', type=int, default=date.today().year)

    sales = Sale.query.filter(
        extract('month', Sale.date) == month,
        extract('year', Sale.date) == year,
    ).order_by(Sale.date).all()

    summary = db.session.query(
        func.sum(Sale.paid),
        func.sum(Sale.discount),
        func.count(Sale.id),
    ).filter(
        extract('month', Sale.date) == month,
        extract('year', Sale.date) == year,
    ).first()

    # Per product breakdown
    product_breakdown = db.session.query(
        Sale.product_id,
        Product.name,
        func.sum(Sale.quantity),
        func.sum(Sale.paid),
    ).join(Product, Sale.product_id == Product.id).filter(
        extract('month', Sale.date) == month,
        extract('year', Sale.date) == year,
    ).group_by(Sale.product_id, Product.name).all()

    return jsonify({
        'month': month,
        'year': year,
        'sales': [s.to_dict() for s in sales],
        'total_revenue': float(summary[0] or 0),
        'total_discounts': float(summary[1] or 0),
        'total_transactions': summary[2] or 0,
        'product_breakdown': [
            {
                'product_id': row[0],
                'product_name': row[1],
                'total_quantity': float(row[2] or 0),
                'total_revenue': float(row[3] or 0),
            }
            for row in product_breakdown
        ],
    }), 200


@reports_bp.route('/weekly', methods=['GET'])
@manager_required
def weekly_report():
    # week_start defaults to this week's Monday
    week_start_str = request.args.get('week_start')
    if week_start_str:
        week_start = date.fromisoformat(week_start_str)
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    sales = Sale.query.filter(
        Sale.date >= week_start, Sale.date <= week_end
    ).order_by(Sale.date).all()

    summary = db.session.query(
        func.sum(Sale.paid),
        func.sum(Sale.discount),
        func.count(Sale.id),
    ).filter(Sale.date >= week_start, Sale.date <= week_end).first()

    product_breakdown = db.session.query(
        Sale.product_id,
        Product.name,
        func.sum(Sale.quantity),
        func.sum(Sale.paid),
    ).join(Product, Sale.product_id == Product.id).filter(
        Sale.date >= week_start, Sale.date <= week_end
    ).group_by(Sale.product_id, Product.name).all()

    return jsonify({
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'sales': [s.to_dict() for s in sales],
        'total_revenue': float(summary[0] or 0),
        'total_discounts': float(summary[1] or 0),
        'total_transactions': summary[2] or 0,
        'product_breakdown': [
            {
                'product_id': row[0],
                'product_name': row[1],
                'total_quantity': float(row[2] or 0),
                'total_revenue': float(row[3] or 0),
            }
            for row in product_breakdown
        ],
    }), 200


@reports_bp.route('/stock-movement', methods=['GET'])
@manager_required
def stock_movement_report():
    sd, ed = _parse_dates()
    query = StockMovement.query
    if sd:
        query = query.filter(StockMovement.date >= sd)
    if ed:
        query = query.filter(StockMovement.date <= ed)

    movements = query.order_by(StockMovement.date.desc()).all()
    return jsonify({'movements': [m.to_dict() for m in movements]}), 200


# ---- PDF exports ----

@reports_bp.route('/daily/pdf', methods=['GET'])
@manager_required
def daily_report_pdf():
    report_date = request.args.get('date', date.today().isoformat())
    d = date.fromisoformat(report_date)
    sales = Sale.query.filter(Sale.date == d).all()
    pdf = generate_sales_pdf(
        [s.to_dict() for s in sales],
        title='Daily Sales Report',
        subtitle=f'Date: {d.isoformat()}',
    )
    return send_file(pdf, mimetype='application/pdf',
                     download_name=f'sales_daily_{d.isoformat()}.pdf')


@reports_bp.route('/monthly/pdf', methods=['GET'])
@manager_required
def monthly_report_pdf():
    month = request.args.get('month', type=int, default=date.today().month)
    year = request.args.get('year', type=int, default=date.today().year)
    sales = Sale.query.filter(
        extract('month', Sale.date) == month,
        extract('year', Sale.date) == year,
    ).all()
    pdf = generate_sales_pdf(
        [s.to_dict() for s in sales],
        title='Monthly Sales Report',
        subtitle=f'Month: {year}-{month:02d}',
    )
    return send_file(pdf, mimetype='application/pdf',
                     download_name=f'sales_monthly_{year}_{month:02d}.pdf')


@reports_bp.route('/weekly/pdf', methods=['GET'])
@manager_required
def weekly_report_pdf():
    week_start_str = request.args.get('week_start')
    if week_start_str:
        week_start = date.fromisoformat(week_start_str)
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    sales = Sale.query.filter(
        Sale.date >= week_start, Sale.date <= week_end
    ).order_by(Sale.date).all()
    pdf = generate_sales_pdf(
        [s.to_dict() for s in sales],
        title='Weekly Sales Report',
        subtitle=f'Week: {week_start.isoformat()} to {week_end.isoformat()}',
    )
    return send_file(pdf, mimetype='application/pdf',
                     download_name=f'sales_weekly_{week_start.isoformat()}.pdf')


@reports_bp.route('/stock-movement/pdf', methods=['GET'])
@manager_required
def stock_movement_pdf():
    sd, ed = _parse_dates()
    query = StockMovement.query
    if sd:
        query = query.filter(StockMovement.date >= sd)
    if ed:
        query = query.filter(StockMovement.date <= ed)
    movements = query.order_by(StockMovement.date.desc()).all()
    pdf = generate_stock_pdf(
        [m.to_dict() for m in movements],
        title='Stock Movement Report',
        subtitle=f'{sd or "All"} to {ed or "Today"}',
    )
    return send_file(pdf, mimetype='application/pdf', download_name='stock_movement.pdf')


@reports_bp.route('/stock-balance/pdf', methods=['GET'])
@manager_required
def stock_balance_pdf():
    from app.routes.stock import stock_balance
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    balances = [
        {
            'product_name': p.name,
            'unit_price': float(p.unit_price),
            'current_stock': p.current_stock(),
            'stock_value': p.current_stock() * float(p.unit_price),
        }
        for p in products
    ]
    pdf = generate_stock_balance_pdf(balances)
    return send_file(pdf, mimetype='application/pdf', download_name='stock_balance.pdf')


# ---- Debt Reports ----

@reports_bp.route('/debts/daily', methods=['GET'])
@manager_required
def daily_debt_report():
    report_date = request.args.get('date', date.today().isoformat())
    d = date.fromisoformat(report_date)

    # Get sales with outstanding debts created on this date
    sales = Sale.query.filter(Sale.date == d).order_by(Sale.created_at).all()
    
    # Summary of debts created on this date
    summary = db.session.query(
        func.sum(Sale.debt),
        func.sum(Sale.paid),
        func.sum(Sale.total),
        func.count(Sale.id),
    ).filter(Sale.date == d).first()

    return jsonify({
        'date': d.isoformat(),
        'sales': [s.to_dict() for s in sales],
        'total_debt_created': float(summary[0] or 0),
        'total_paid': float(summary[1] or 0),
        'total_amount': float(summary[2] or 0),
        'debt_count': summary[3] or 0,
    }), 200


@reports_bp.route('/debts/weekly', methods=['GET'])
@manager_required
def weekly_debt_report():
    week_start_str = request.args.get('week_start')
    if week_start_str:
        week_start = date.fromisoformat(week_start_str)
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    sales = Sale.query.filter(
        Sale.date >= week_start, Sale.date <= week_end
    ).order_by(Sale.date).all()

    summary = db.session.query(
        func.sum(Sale.debt),
        func.sum(Sale.paid),
        func.sum(Sale.total),
        func.count(Sale.id),
    ).filter(Sale.date >= week_start, Sale.date <= week_end).first()

    return jsonify({
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'sales': [s.to_dict() for s in sales],
        'total_debt_created': float(summary[0] or 0),
        'total_paid': float(summary[1] or 0),
        'total_amount': float(summary[2] or 0),
        'debt_count': summary[3] or 0,
    }), 200


@reports_bp.route('/debts/monthly', methods=['GET'])
@manager_required
def monthly_debt_report():
    month = request.args.get('month', type=int, default=date.today().month)
    year = request.args.get('year', type=int, default=date.today().year)

    sales = Sale.query.filter(
        extract('month', Sale.date) == month,
        extract('year', Sale.date) == year,
    ).order_by(Sale.date).all()

    summary = db.session.query(
        func.sum(Sale.debt),
        func.sum(Sale.paid),
        func.sum(Sale.total),
        func.count(Sale.id),
    ).filter(
        extract('month', Sale.date) == month,
        extract('year', Sale.date) == year,
    ).first()

    return jsonify({
        'month': month,
        'year': year,
        'sales': [s.to_dict() for s in sales],
        'total_debt_created': float(summary[0] or 0),
        'total_paid': float(summary[1] or 0),
        'total_amount': float(summary[2] or 0),
        'debt_count': summary[3] or 0,
    }), 200
