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
    gender = db.Column(db.String(10), nullable=True)  # 'male' | 'female' | None
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # For sellers: tracks which manager created/owns them (independent of shop assignment)
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

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
        """Return list of active shop IDs accessible to this user."""
        if self.is_super_admin:
            from app.models.shop import Shop
            return [s.id for s in Shop.query.filter_by(is_active=True).all()]
        if self.is_manager:
            # Manager sees only shops they own
            from app.models.shop import Shop
            return [s.id for s in Shop.query.filter_by(owner_id=self.id, is_active=True).all()]
        # Seller sees only assigned shops
        return [s.id for s in self.shops.filter_by(is_active=True).all()]

    def to_dict(self):
        shop_ids = [] if self.is_super_admin else self.get_shop_ids()
        manager_name = None
        if self.manager_id:
            mgr = User.query.get(self.manager_id)
            manager_name = mgr.full_name or mgr.username if mgr else None
        # For sellers, include first assigned shop's name and location for display
        shop_name = None
        shop_location = None
        if self.is_seller:
            first_shop = self.shops.first()
            if first_shop:
                shop_name = first_shop.name
                shop_location = first_shop.location
        return {
            'id': self.id,
            'username': self.username,
            'role': self.effective_role,
            'full_name': self.full_name,
            'gender': self.gender,
            'is_active': self.is_active,
            'shop_ids': shop_ids,
            'shop_name': shop_name,
            'shop_location': shop_location,
            'created_at': self.created_at.isoformat(),
            'manager_id': self.manager_id,
            'manager_name': manager_name,
        }
