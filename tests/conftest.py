import pytest
from app import create_app, db as _db
from app.models.user import User


@pytest.fixture(scope='session')
def app():
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'JWT_SECRET_KEY': 'test-secret',
    })
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture(scope='function')
def db(app):
    with app.app_context():
        yield _db
        _db.session.rollback()


@pytest.fixture(scope='function')
def client(app):
    return app.test_client()


@pytest.fixture(scope='function')
def manager_token(client, db):
    user = User(username='test_manager', role='manager', full_name='Test Manager')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    resp = client.post('/api/auth/login', json={
        'username': 'test_manager',
        'password': 'password123',
    })
    return resp.get_json()['access_token']


@pytest.fixture(scope='function')
def auth_headers(manager_token):
    return {'Authorization': f'Bearer {manager_token}'}
