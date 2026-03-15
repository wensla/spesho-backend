from app import db
from datetime import datetime


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    unit = db.Column(db.String(20), nullable=False, default='kg')
    package_size = db.Column(db.Integer, nullable=False, default=5)
    category = db.Column(db.String(20), nullable=False, default='unga')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shop = db.relationship('Shop', foreign_keys=[shop_id])
    stock_movements = db.relationship('StockMovement', backref='product', lazy=True)
    sales = db.relationship('Sale', backref='product', lazy=True)

    def current_stock(self, shop_id=None):
        from sqlalchemy import func
        from app.models.stock_movement import StockMovement
        q = db.session.query(
            func.coalesce(func.sum(StockMovement.quantity_in), 0) -
            func.coalesce(func.sum(StockMovement.quantity_out), 0)
        ).filter(StockMovement.product_id == self.id)
        if shop_id:
            q = q.filter(StockMovement.shop_id == shop_id)
        result = q.scalar()
        return float(result or 0)

    def to_dict(self, include_stock=False, shop_id=None):
        data = {
            'id': self.id,
            'shop_id': self.shop_id,
            'name': self.name,
            'unit_price': float(self.unit_price),
            'unit': self.unit,
            'package_size': self.package_size,
            'category': self.category,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
        }
        if include_stock:
            data['current_stock'] = self.current_stock(shop_id=shop_id or self.shop_id)
        return data
