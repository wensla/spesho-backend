from app import db
from datetime import datetime


class Sale(db.Model):
    __tablename__ = 'sales'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    quantity = db.Column(db.Numeric(12, 2), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    discount = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(14, 2), nullable=False)
    paid = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    debt = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    payment_method = db.Column(db.String(20), nullable=False, default='cash')
    note = db.Column(db.String(255), nullable=True)
    sold_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    date = db.Column(db.Date, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    shop = db.relationship('Shop', foreign_keys=[shop_id])

    def to_dict(self):
        return {
            'id': self.id,
            'shop_id': self.shop_id,
            'shop_name': self.shop.name if self.shop else None,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else None,
            'quantity': float(self.quantity),
            'price': float(self.price),
            'discount': float(self.discount or 0),
            'total': float(self.total),
            'paid': float(self.paid or 0),
            'debt': float(self.debt or 0),
            'payment_method': self.payment_method or 'cash',
            'note': self.note,
            'sold_by': self.sold_by,
            'sold_by_name': self.salesperson.username if self.salesperson else None,
            'date': self.date.isoformat() if self.date else None,
            'created_at': self.created_at.isoformat(),
        }
