from app import db
from datetime import datetime


class DailySale(db.Model):
    __tablename__ = 'daily_sales'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    total_amount = db.Column(db.Numeric(14, 2), nullable=False)
    cash_paid = db.Column(db.Numeric(14, 2), nullable=False)
    debt = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    note = db.Column(db.String(255), nullable=True)
    customer_name = db.Column(db.String(100), nullable=True)
    customer_phone = db.Column(db.String(30), nullable=True)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    recorder = db.relationship('User', foreign_keys=[recorded_by])

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'total_amount': float(self.total_amount),
            'cash_paid': float(self.cash_paid),
            'debt': float(self.debt),
            'note': self.note,
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone,
            'recorded_by': self.recorded_by,
            'recorded_by_name': self.recorder.username if self.recorder else None,
            'created_at': self.created_at.isoformat(),
        }
