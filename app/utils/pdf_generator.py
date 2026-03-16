from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from io import BytesIO
from datetime import datetime


def _build_header(title, subtitle=''):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', fontSize=16, fontName='Helvetica-Bold', alignment=TA_CENTER)
    sub_style   = ParagraphStyle('Sub', fontSize=10, fontName='Helvetica', alignment=TA_CENTER, textColor=colors.grey)
    elements = [
        Paragraph('SPESHO PRODUCTS MANAGEMENT SYSTEM', title_style),
        Spacer(1, 0.3 * cm),
        Paragraph(title, ParagraphStyle('ReportTitle', fontSize=13, fontName='Helvetica-Bold', alignment=TA_CENTER)),
    ]
    if subtitle:
        elements.append(Paragraph(subtitle, sub_style))
    elements.append(Paragraph(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}', sub_style))
    elements.append(Spacer(1, 0.5 * cm))
    return elements


def _table_style(header_color='#1a237e'):
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(header_color)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ])


# ── Legacy: line-item sales PDF (used by some old routes) ─────────────────────
def generate_sales_pdf(sales, title, subtitle=''):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = _build_header(title, subtitle)

    headers = ['#', 'Date', 'Product', 'Qty', 'Price', 'Discount', 'Total', 'Sold By']
    data = [headers]
    grand_total = 0
    grand_discount = 0

    for i, sale in enumerate(sales, 1):
        data.append([
            str(i),
            sale.get('date', ''),
            sale.get('product_name', ''),
            f"{sale.get('quantity', 0):.0f}",
            f"{sale.get('price', 0):,.2f}",
            f"{sale.get('discount', 0):,.2f}",
            f"{sale.get('total', 0):,.2f}",
            sale.get('sold_by_name', ''),
        ])
        grand_total    += float(sale.get('total', 0))
        grand_discount += float(sale.get('discount', 0))

    data.append(['', '', '', '', '', 'TOTAL DISCOUNT', f'{grand_discount:,.2f}', ''])
    data.append(['', '', '', '', '', 'GRAND TOTAL',    f'{grand_total:,.2f}', ''])

    col_widths = [1*cm, 2.2*cm, 4*cm, 1.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = _table_style()
    style.add('FONTNAME',   (0, -2), (-1, -1), 'Helvetica-Bold')
    style.add('BACKGROUND', (0, -2), (-1, -1), colors.HexColor('#e3f2fd'))
    table.setStyle(style)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ── DailySale-based sales PDF (daily / weekly / monthly) ─────────────────────
def generate_daily_sales_pdf(sales, title, subtitle=''):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = _build_header(title, subtitle)

    headers = ['#', 'Date', 'Customer', 'Total (TZS)', 'Cash Paid', 'Debt', 'Payment', 'Shop']
    data = [headers]
    grand_total = 0
    grand_cash  = 0
    grand_debt  = 0

    for i, s in enumerate(sales, 1):
        data.append([
            str(i),
            s.get('date', ''),
            s.get('customer_name', '-'),
            f"{float(s.get('total_amount', 0)):,.2f}",
            f"{float(s.get('cash_paid', 0)):,.2f}",
            f"{float(s.get('debt', 0)):,.2f}",
            s.get('payment_label', s.get('payment_method', '')),
            s.get('shop_name', ''),
        ])
        grand_total += float(s.get('total_amount', 0))
        grand_cash  += float(s.get('cash_paid', 0))
        grand_debt  += float(s.get('debt', 0))

    data.append(['', '', 'TOTALS', f'{grand_total:,.2f}', f'{grand_cash:,.2f}',
                 f'{grand_debt:,.2f}', '', ''])

    col_widths = [1*cm, 2.2*cm, 3.5*cm, 2.8*cm, 2.8*cm, 2.3*cm, 2.2*cm, 2.5*cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = _table_style()
    style.add('FONTNAME',   (0, -1), (-1, -1), 'Helvetica-Bold')
    style.add('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e3f2fd'))
    table.setStyle(style)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ── Yearly report PDF ─────────────────────────────────────────────────────────
def generate_yearly_report_pdf(month_rows, year):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = _build_header('Yearly Sales Report', subtitle=f'Year: {year}')

    headers = ['Month', 'Total Revenue', 'Cash Paid', 'Debt', 'Transactions']
    data = [headers]
    grand_total = 0
    grand_cash  = 0
    grand_debt  = 0

    for r in month_rows:
        data.append([
            r['month'],
            f"{r['total']:,.2f}",
            f"{r['cash_paid']:,.2f}",
            f"{r['debt']:,.2f}",
            str(r['count']),
        ])
        grand_total += r['total']
        grand_cash  += r['cash_paid']
        grand_debt  += r['debt']

    data.append(['TOTAL', f'{grand_total:,.2f}', f'{grand_cash:,.2f}', f'{grand_debt:,.2f}', ''])

    col_widths = [3*cm, 4.5*cm, 4.5*cm, 3.5*cm, 3.5*cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = _table_style()
    style.add('FONTNAME',   (0, -1), (-1, -1), 'Helvetica-Bold')
    style.add('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e3f2fd'))
    table.setStyle(style)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ── Multi-shop summary PDF ────────────────────────────────────────────────────
def generate_shop_summary_pdf(shop_data, month, year):
    MONTH_NAMES = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = _build_header(
        'Multi-Shop Sales Summary',
        subtitle=f'{MONTH_NAMES[month]} {year}'
    )

    headers = ['Shop', 'Total Revenue', 'Cash Paid', 'Debt', 'Transactions']
    data = [headers]
    grand_total = 0

    for s in shop_data:
        data.append([
            s['shop_name'],
            f"{s['total']:,.2f}",
            f"{s['cash_paid']:,.2f}",
            f"{s['debt']:,.2f}",
            str(s['transactions']),
        ])
        grand_total += s['total']

    data.append(['TOTAL', f'{grand_total:,.2f}', '', '', ''])

    col_widths = [5*cm, 4*cm, 4*cm, 3*cm, 3*cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = _table_style()
    style.add('FONTNAME',   (0, -1), (-1, -1), 'Helvetica-Bold')
    style.add('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e3f2fd'))
    table.setStyle(style)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ── Stock movement PDF ────────────────────────────────────────────────────────
def generate_stock_pdf(movements, title, subtitle=''):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = _build_header(title, subtitle)

    headers = ['#', 'Date', 'Product', 'In', 'Out', 'Unit Price', 'Type', 'Reason']
    data = [headers]

    for i, m in enumerate(movements, 1):
        data.append([
            str(i),
            m.get('date', ''),
            m.get('product_name', ''),
            f"{m.get('quantity_in', 0):.0f}",
            f"{m.get('quantity_out', 0):.0f}",
            f"{m.get('unit_price', 0):,.2f}" if m.get('unit_price') else '-',
            m.get('movement_type', '').upper(),
            m.get('reason', '') or '',
        ])

    col_widths = [1*cm, 2.2*cm, 3.8*cm, 1.8*cm, 1.8*cm, 2.2*cm, 2*cm, 3.2*cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(_table_style())
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ── Stock balance PDF ─────────────────────────────────────────────────────────
def generate_stock_balance_pdf(balances, title='Stock Balance Report'):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = _build_header(title)

    headers = ['#', 'Product', 'Sell Price', 'Buy Price', 'Current Stock', 'Stock Value']
    data = [headers]
    total_value = 0

    for i, b in enumerate(balances, 1):
        bp = b.get('buying_price')
        data.append([
            str(i),
            b.get('product_name', ''),
            f"{b.get('unit_price', 0):,.2f}",
            f"{bp:,.2f}" if bp else '-',
            f"{b.get('current_stock', 0):.2f}",
            f"{b.get('stock_value', 0):,.2f}",
        ])
        total_value += float(b.get('stock_value', 0))

    data.append(['', '', '', '', 'TOTAL VALUE', f'{total_value:,.2f}'])

    col_widths = [1*cm, 5*cm, 2.8*cm, 2.5*cm, 3*cm, 3*cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = _table_style()
    style.add('FONTNAME',   (0, -1), (-1, -1), 'Helvetica-Bold')
    style.add('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e3f2fd'))
    table.setStyle(style)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ── Debts PDF ─────────────────────────────────────────────────────────────────
def generate_debts_pdf(debts, status=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    subtitle = f'Status: {status.upper()}' if status else 'All Debts'
    elements = _build_header('Credit & Debt Report', subtitle=subtitle)

    headers = ['#', 'Date', 'Customer', 'Product', 'Total', 'Paid', 'Balance', 'Status', 'Days']
    data = [headers]
    grand_balance = 0

    for i, d in enumerate(debts, 1):
        data.append([
            str(i),
            d.get('date', ''),
            d.get('customer_name', ''),
            d.get('product_name', '') or '-',
            f"{d.get('total_amount', 0):,.2f}",
            f"{d.get('amount_paid', 0):,.2f}",
            f"{d.get('balance', 0):,.2f}",
            d.get('status', '').upper(),
            str(d.get('days_outstanding', 0)) if d.get('status') != 'paid' else '-',
        ])
        if d.get('status') != 'paid':
            grand_balance += float(d.get('balance', 0))

    data.append(['', '', '', '', '', 'OUTSTANDING', f'{grand_balance:,.2f}', '', ''])

    col_widths = [1*cm, 2.2*cm, 3.2*cm, 2.8*cm, 2.5*cm, 2.5*cm, 2.5*cm, 1.8*cm, 1.2*cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = _table_style(header_color='#b71c1c')
    style.add('FONTNAME',   (0, -1), (-1, -1), 'Helvetica-Bold')
    style.add('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fce4ec'))
    table.setStyle(style)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer
