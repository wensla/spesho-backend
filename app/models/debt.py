from app import db
from datetime import datetime, date as date_cls


class Debt(db.Model):
    __tablename__ = 'debts'

    id            = db.Column(db.Integer, primary_key=True)
    shop_id       = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True, index=True)
    seller_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone= db.Column(db.String(20),  nullable=True)
    product_id    = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True, index=True)
    quantity      = db.Column(db.Numeric(12, 2), nullable=True)
    unit_price    = db.Column(db.Numeric(12, 2), nullable=True)
    total_amount  = db.Column(db.Numeric(14, 2), nullable=False)
    amount_paid   = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    note          = db.Column(db.String(255), nullable=True)
    date          = db.Column(db.Date, default=date_cls.today, nullable=False, index=True)
    status        = db.Column(db.String(10), default='pending', nullable=False, index=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    shop     = db.relationship('Shop', foreign_keys=[shop_id])
    product  = db.relationship('Product', backref='debts', lazy='joined')
    payments = db.relationship('DebtPayment', backref='debt', lazy='dynamic',
                               cascade='all, delete-orphan')

    @property
    def balance(self):
        return float(self.total_amount) - float(self.amount_paid or 0)

    @property
    def days_outstanding(self):
        if self.status == 'paid' or not self.date:
            return 0
        return (date_cls.today() - self.date).days

    def to_dict(self):
        return {
            'id':              self.id,
            'shop_id':         self.shop_id,
            'shop_name':       self.shop.name if self.shop else None,
            'seller_id':       self.seller_id,
            'customer_name':   self.customer_name,
            'customer_phone':  self.customer_phone,
            'product_id':      self.product_id,
            'product_name':    self.product.name if self.product else None,
            'quantity':        float(self.quantity)   if self.quantity   else None,
            'unit_price':      float(self.unit_price) if self.unit_price else None,
            'total_amount':    float(self.total_amount),
            'amount_paid':     float(self.amount_paid or 0),
            'balance':         self.balance,
            'note':            self.note,
            'date':            self.date.isoformat() if self.date else None,
            'status':          self.status,
            'days_outstanding': self.days_outstanding,
            'created_at':      self.created_at.isoformat(),
        }


class DebtPayment(db.Model):
    __tablename__ = 'debt_payments'

    id           = db.Column(db.Integer, primary_key=True)
    debt_id      = db.Column(db.Integer, db.ForeignKey('debts.id'), nullable=False, index=True)
    amount       = db.Column(db.Numeric(14, 2), nullable=False)
    note         = db.Column(db.String(255), nullable=True)
    payment_date = db.Column(db.Date, default=date_cls.today, nullable=False, index=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':           self.id,
            'debt_id':      self.debt_id,
            'amount':       float(self.amount),
            'note':         self.note,
            'payment_date': self.payment_date.isoformat() if self.payment_date else None,
            'created_at':   self.created_at.isoformat(),
        }
