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

    from app.models import user, product, stock_movement, sale, debt, daily_sale  # noqa: F401

    from app.routes.auth import auth_bp
    from app.routes.products import products_bp
    from app.routes.stock import stock_bp
    from app.routes.sales import sales_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.reports import reports_bp
    from app.routes.users import users_bp
    from app.routes.daily_sales import daily_sales_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(products_bp, url_prefix='/api/products')
    app.register_blueprint(stock_bp, url_prefix='/api/stock')
    app.register_blueprint(sales_bp, url_prefix='/api/sales')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    from app.routes.debts import debts_bp
    app.register_blueprint(debts_bp, url_prefix='/api/debts')
    app.register_blueprint(daily_sales_bp, url_prefix='/api/daily-sales')

    @app.route('/api/health')
    def health():
        return {'status': 'ok', 'message': 'Spesho API running'}

    with app.app_context():
        db.create_all()
        _seed_admin()

    return app


def _seed_admin():
    from app.models.user import User
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='manager', full_name='System Admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
