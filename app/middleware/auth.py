from functools import wraps
from flask import jsonify, g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from app.models.user import User


def _load_user():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if user:
        g.current_user = user
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = _load_user()
        if not user or not user.is_active:
            return jsonify({'error': 'Unauthorized'}), 401
        return fn(*args, **kwargs)
    return wrapper


def manager_required(fn):
    """Allows manager and super_admin."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = _load_user()
        if not user or user.effective_role not in ('manager', 'super_admin'):
            return jsonify({'error': 'Manager access required'}), 403
        return fn(*args, **kwargs)
    return wrapper


def super_admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = _load_user()
        if not user or not user.is_super_admin:
            return jsonify({'error': 'Super Admin access required'}), 403
        return fn(*args, **kwargs)
    return wrapper


def get_current_user():
    """Return current user from g (set by any auth decorator) or fetch fresh."""
    if hasattr(g, 'current_user'):
        return g.current_user
    user_id = int(get_jwt_identity())
    return User.query.get(user_id)
