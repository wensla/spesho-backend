from app import create_app, db
from app.models.user import User

app = create_app()


@app.cli.command('seed')
def seed_db():
    """Seed database with default manager account."""
    with app.app_context():
        if not User.query.filter_by(username='admin').first():
            manager = User(username='admin', role='manager', full_name='System Admin')
            manager.set_password('admin123')
            db.session.add(manager)
            db.session.commit()
            print('Default manager created: admin / admin123')
        else:
            print('Admin already exists.')


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
