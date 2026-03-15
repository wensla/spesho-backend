from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Many-to-many: users ↔ shops — defined here to avoid circular imports
_user_shops = db.Table(
    'user_shops',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('shop_id', db.Integer, db.ForeignKey('shops.id'), primary_key=True),
)


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    # Roles: 'super_admin' | 'manager' | 'seller'
    # Legacy 'salesperson' is treated as 'seller' everywhere
    role = db.Column(db.String(20), nullable=False, default='seller')
    full_name = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sales = db.relationship('Sale', backref='salesperson', lazy=True)

    # Many-to-many shops (not applicable to super_admin)
    shops = db.relationship(
        'Shop',
        secondary=_user_shops,
        backref=db.backref('users', lazy='dynamic'),
        lazy='dynamic',
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def effective_role(self):
        """Normalise legacy 'salesperson' to 'seller'."""
        return 'seller' if self.role == 'salesperson' else self.role

    @property
    def is_super_admin(self):
        return self.effective_role == 'super_admin'

    @property
    def is_manager(self):
        return self.effective_role == 'manager'

    @property
    def is_seller(self):
        return self.effective_role == 'seller'

    def get_shop_ids(self):
        """Return list of shop IDs this user belongs to. Super admins get all."""
        if self.is_super_admin:
            from app.models.shop import Shop
            return [s.id for s in Shop.query.filter_by(is_active=True).all()]
        return [s.id for s in self.shops.all()]

    def to_dict(self):
        shop_ids = [] if self.is_super_admin else [s.id for s in self.shops.all()]
        return {
            'id': self.id,
            'username': self.username,
            'role': self.effective_role,
            'full_name': self.full_name,
            'is_active': self.is_active,
            'shop_ids': shop_ids,
            'created_at': self.created_at.isoformat(),
        }
