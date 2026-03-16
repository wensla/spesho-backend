from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_migrate import Migrate
from dotenv import load_dotenv
import os

load_dotenv()

db = SQLAlchemy()
jwt = JWTManager()
migrate = Migrate()


def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-jwt-secret')
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/spesho_db')
    # Render provides 'postgres://' but SQLAlchemy requires 'postgresql://'
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 86400))

    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    CORS(app)

    # Import all models so SQLAlchemy knows about them
    from app.models import user, shop, user_shop, product, stock_movement, sale, debt, daily_sale  # noqa: F401

    from app.routes.auth import auth_bp
    from app.routes.products import products_bp
    from app.routes.stock import stock_bp
    from app.routes.sales import sales_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.reports import reports_bp
    from app.routes.users import users_bp
    from app.routes.daily_sales import daily_sales_bp
    from app.routes.shops import shops_bp
    from app.routes.debts import debts_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(products_bp, url_prefix='/api/products')
    app.register_blueprint(stock_bp, url_prefix='/api/stock')
    app.register_blueprint(sales_bp, url_prefix='/api/sales')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(daily_sales_bp, url_prefix='/api/daily-sales')
    app.register_blueprint(shops_bp, url_prefix='/api/shops')
    app.register_blueprint(debts_bp, url_prefix='/api/debts')

    @app.route('/api/health')
    def health():
        return {'status': 'ok', 'message': 'Spesho API running'}

    with app.app_context():
        db.create_all()
        _run_migrations()
        _seed_default_shop_and_admin()

    return app


def _run_migrations():
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)

    # ── users: add gender ─────────────────────────────────────────────────────
    u_cols = [c['name'] for c in inspector.get_columns('users')]
    with db.engine.connect() as conn:
        if 'gender' not in u_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN gender VARCHAR(10)"))
            conn.commit()

    # ── shops: add owner_id ───────────────────────────────────────────────────
    if 'shops' in inspector.get_table_names():
        sh_cols = [c['name'] for c in inspector.get_columns('shops')]
        with db.engine.connect() as conn:
            if 'owner_id' not in sh_cols:
                conn.execute(text('ALTER TABLE shops ADD COLUMN owner_id INTEGER REFERENCES users(id)'))
                conn.commit()

    # ── products ──────────────────────────────────────────────────────────────
    cols = [c['name'] for c in inspector.get_columns('products')]
    with db.engine.connect() as conn:
        if 'package_size' not in cols:
            conn.execute(text('ALTER TABLE products ADD COLUMN package_size INTEGER NOT NULL DEFAULT 5'))
            conn.commit()
        if 'category' not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN category VARCHAR(20) NOT NULL DEFAULT 'unga'"))
            conn.commit()
        if 'shop_id' not in cols:
            conn.execute(text('ALTER TABLE products ADD COLUMN shop_id INTEGER REFERENCES shops(id)'))
            conn.commit()

    # ── daily_sales ───────────────────────────────────────────────────────────
    if 'daily_sales' in inspector.get_table_names():
        ds_cols = [c['name'] for c in inspector.get_columns('daily_sales')]
        with db.engine.connect() as conn:
            if 'shop_id' not in ds_cols:
                conn.execute(text('ALTER TABLE daily_sales ADD COLUMN shop_id INTEGER REFERENCES shops(id)'))
                conn.commit()
            if 'payment_method' not in ds_cols:
                conn.execute(text("ALTER TABLE daily_sales ADD COLUMN payment_method VARCHAR(20) NOT NULL DEFAULT 'cash'"))
                conn.commit()

    # ── sales ─────────────────────────────────────────────────────────────────
    if 'sales' in inspector.get_table_names():
        s_cols = [c['name'] for c in inspector.get_columns('sales')]
        with db.engine.connect() as conn:
            if 'shop_id' not in s_cols:
                conn.execute(text('ALTER TABLE sales ADD COLUMN shop_id INTEGER REFERENCES shops(id)'))
                conn.commit()
            if 'payment_method' not in s_cols:
                conn.execute(text("ALTER TABLE sales ADD COLUMN payment_method VARCHAR(20) NOT NULL DEFAULT 'cash'"))
                conn.commit()

    # ── stock_movements ───────────────────────────────────────────────────────
    if 'stock_movements' in inspector.get_table_names():
        sm_cols = [c['name'] for c in inspector.get_columns('stock_movements')]
        with db.engine.connect() as conn:
            if 'shop_id' not in sm_cols:
                conn.execute(text('ALTER TABLE stock_movements ADD COLUMN shop_id INTEGER REFERENCES shops(id)'))
                conn.commit()

    # ── users: add manager_id for seller→manager tracking ────────────────────
    u_cols2 = [c['name'] for c in inspector.get_columns('users')]
    with db.engine.connect() as conn:
        if 'manager_id' not in u_cols2:
            conn.execute(text('ALTER TABLE users ADD COLUMN manager_id INTEGER REFERENCES users(id)'))
            conn.commit()

    # ── users: normalise legacy 'salesperson' role ────────────────────────────
    # Drop old check constraint (if any) before updating the role value
    with db.engine.connect() as conn:
        conn.execute(text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'users_role_check'
                ) THEN
                    ALTER TABLE users DROP CONSTRAINT users_role_check;
                END IF;
            END$$
        """))
        conn.commit()
        conn.execute(text("UPDATE users SET role = 'seller' WHERE role = 'salesperson'"))
        conn.commit()
        # Add updated check constraint
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'users_role_check_v2'
                ) THEN
                    ALTER TABLE users ADD CONSTRAINT users_role_check_v2
                        CHECK (role IN ('super_admin', 'manager', 'seller'));
                END IF;
            END$$
        """))
        conn.commit()


def _seed_default_shop_and_admin():
    from app.models.user import User

    # Super Admin = system owner, no shop assignment
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', role='super_admin', full_name='System Admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
    else:
        if admin.role in ('manager', 'salesperson', 'seller'):
            admin.role = 'super_admin'
            db.session.commit()
