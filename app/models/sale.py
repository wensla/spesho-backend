from app import db
from datetime import datetime


class Sale(db.Model):
    __tablename__ = 'sales'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    quantity = db.Column(db.Numeric(12, 2), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    discount = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(14, 2), nullable=False)
    paid = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    debt = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    note = db.Column(db.String(255), nullable=True)
    sold_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    date = db.Column(db.Date, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else None,
            'quantity': float(self.quantity),
            'price': float(self.price),
            'discount': float(self.discount or 0),
            'total': float(self.total),
            'paid': float(self.paid or 0),
            'debt': float(self.debt or 0),
            'note': self.note,
            'sold_by': self.sold_by,
            'sold_by_name': self.salesperson.username if self.salesperson else None,
            'date': self.date.isoformat() if self.date else None,
            'created_at': self.created_at.isoformat(),
        }
