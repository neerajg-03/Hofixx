from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import User

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard/user/new')
@jwt_required(optional=True)
def user_dashboard_new():
    """New user dashboard with all functionalities"""
    # Check if user is admin and redirect them
    try:
        ident = get_jwt_identity()
        if ident:
            user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
            user = User.objects(id=user_id).first()
            if user and user.role == 'admin':
                return redirect('/admin')
    except Exception:
        pass  # Continue to render dashboard if check fails
    return render_template('dashboard_user_new.html')

@dashboard_bp.route('/dashboard/user')
@jwt_required()
def user_dashboard():
    """Redirect to new user dashboard"""
    from flask import redirect, url_for
    print("DEBUG: /dashboard/user route called, redirecting to new dashboard")
    return redirect(url_for('dashboard.user_dashboard_new'))

@dashboard_bp.route('/dashboard-provider')
def provider_dashboard():
    """Provider dashboard with chat functionality"""
    # Let the frontend handle authentication
    # The JavaScript will check for the token and redirect if needed
    return render_template('dashboard_provider.html')


