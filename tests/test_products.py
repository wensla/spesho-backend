import pytest
from app import db
from app.models.product import Product


@pytest.fixture(autouse=True)
def clean_products(app):
    with app.app_context():
        yield
        db.session.query(Product).filter(Product.name.like('Test_%')).delete()
        db.session.commit()


class TestListProducts:
    def test_list_products_requires_auth(self, client):
        resp = client.get('/api/products/')
        assert resp.status_code == 401

    def test_list_products_returns_list(self, client, auth_headers, app):
        with app.app_context():
            p = Product(name='Test_Sembe', unit_price=1200)
            db.session.add(p)
            db.session.commit()

        resp = client.get('/api/products/', headers=auth_headers)
        assert resp.status_code == 200
        names = [p['name'] for p in resp.get_json()['products']]
        assert 'Test_Sembe' in names


class TestCreateProduct:
    def test_create_product_success(self, client, auth_headers):
        resp = client.post('/api/products/', json={
            'name': 'Test_Dona',
            'unit_price': 950,
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['product']['name'] == 'Test_Dona'
        assert data['product']['unit_price'] == 950

    def test_create_product_missing_name(self, client, auth_headers):
        resp = client.post('/api/products/', json={
            'unit_price': 950,
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_create_product_whitespace_name(self, client, auth_headers):
        resp = client.post('/api/products/', json={
            'name': '   ',
            'unit_price': 950,
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_create_product_zero_price(self, client, auth_headers):
        resp = client.post('/api/products/', json={
            'name': 'Test_Zero',
            'unit_price': 0,
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_create_product_negative_price(self, client, auth_headers):
        resp = client.post('/api/products/', json={
            'name': 'Test_Neg',
            'unit_price': -100,
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_create_duplicate_product(self, client, auth_headers):
        client.post('/api/products/', json={
            'name': 'Test_Dup',
            'unit_price': 500,
        }, headers=auth_headers)
        resp = client.post('/api/products/', json={
            'name': 'Test_Dup',
            'unit_price': 600,
        }, headers=auth_headers)
        assert resp.status_code == 409


class TestUpdateProduct:
    def test_update_product_name(self, client, auth_headers, app):
        create_resp = client.post('/api/products/', json={
            'name': 'Test_Update',
            'unit_price': 800,
        }, headers=auth_headers)
        product_id = create_resp.get_json()['product']['id']

        resp = client.put(f'/api/products/{product_id}', json={
            'name': 'Test_Updated',
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()['product']['name'] == 'Test_Updated'

    def test_update_product_zero_price_rejected(self, client, auth_headers):
        create_resp = client.post('/api/products/', json={
            'name': 'Test_PriceUpdate',
            'unit_price': 800,
        }, headers=auth_headers)
        product_id = create_resp.get_json()['product']['id']

        resp = client.put(f'/api/products/{product_id}', json={
            'unit_price': 0,
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_update_nonexistent_product(self, client, auth_headers):
        resp = client.put('/api/products/999999', json={
            'name': 'Ghost',
        }, headers=auth_headers)
        assert resp.status_code == 404


class TestDeleteProduct:
    def test_delete_product(self, client, auth_headers):
        create_resp = client.post('/api/products/', json={
            'name': 'Test_Delete',
            'unit_price': 500,
        }, headers=auth_headers)
        product_id = create_resp.get_json()['product']['id']

        resp = client.delete(f'/api/products/{product_id}',
                             headers=auth_headers)
        assert resp.status_code == 200

        list_resp = client.get('/api/products/', headers=auth_headers)
        names = [p['name'] for p in list_resp.get_json()['products']]
        assert 'Test_Delete' not in names
