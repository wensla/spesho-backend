from app import db
from datetime import datetime


class StockMovement(db.Model):
    __tablename__ = 'stock_movements'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    quantity_in = db.Column(db.Numeric(12, 2), default=0)
    quantity_out = db.Column(db.Numeric(12, 2), default=0)
    unit_price = db.Column(db.Numeric(12, 2), nullable=True)
    note = db.Column(db.String(255), nullable=True)
    movement_type = db.Column(db.String(10), nullable=False)  # 'in' | 'out'
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    date = db.Column(db.Date, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else None,
            'quantity_in': float(self.quantity_in or 0),
            'quantity_out': float(self.quantity_out or 0),
            'unit_price': float(self.unit_price) if self.unit_price else None,
            'note': self.note,
            'movement_type': self.movement_type,
            'created_by': self.created_by,
            'date': self.date.isoformat() if self.date else None,
            'created_at': self.created_at.isoformat(),
        }
