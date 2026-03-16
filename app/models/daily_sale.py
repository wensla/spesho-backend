from app import db
from datetime import datetime

# Payment method choices
PAYMENT_METHODS = (
    'cash',
    'mpesa',          # M-Pesa
    'tigopesa',       # Tigo Pesa
    'airtel_money',   # Airtel Money
    'mobile_money',   # legacy / generic fallback
    'bank_transfer',
    'credit',
)

PAYMENT_LABELS = {
    'cash':          'Cash',
    'mpesa':         'M-Pesa',
    'tigopesa':      'Tigo Pesa',
    'airtel_money':  'Airtel Money',
    'mobile_money':  'Mobile Money',
    'bank_transfer': 'Bank Transfer',
    'credit':        'Credit',
}


class DailySale(db.Model):
    __tablename__ = 'daily_sales'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    total_amount = db.Column(db.Numeric(14, 2), nullable=False)
    cash_paid = db.Column(db.Numeric(14, 2), nullable=False)
    debt = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    payment_method = db.Column(db.String(20), nullable=False, default='cash')
    note = db.Column(db.String(255), nullable=True)
    customer_name = db.Column(db.String(100), nullable=True)
    customer_phone = db.Column(db.String(30), nullable=True)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    recorder = db.relationship('User', foreign_keys=[recorded_by])
    shop = db.relationship('Shop', foreign_keys=[shop_id])

    def to_dict(self):
        return {
            'id': self.id,
            'shop_id': self.shop_id,
            'shop_name': self.shop.name if self.shop else None,
            'date': self.date.isoformat(),
            'total_amount': float(self.total_amount),
            'cash_paid': float(self.cash_paid),
            'debt': float(self.debt),
            'payment_method': self.payment_method or 'cash',
            'payment_label': PAYMENT_LABELS.get(self.payment_method or 'cash', self.payment_method or 'Cash'),
            'note': self.note,
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone,
            'recorded_by': self.recorded_by,
            'recorded_by_name': self.recorder.username if self.recorder else None,
            'created_at': self.created_at.isoformat(),
        }
