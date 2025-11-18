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
@jwt_required(optional=True)
def provider_dashboard():
    """Provider dashboard with chat functionality"""
    # Check authentication but don't force redirect - let frontend handle it
    try:
        ident = get_jwt_identity()
        if ident:
            user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
            from bson import ObjectId
            try:
                user = User.objects(id=ObjectId(user_id)).first()
            except:
                user = User.objects(id=user_id).first()
            if user and user.role == 'provider':
                # User is authenticated and is a provider
                return render_template('dashboard_provider.html')
    except Exception as e:
        print(f"Error checking auth in provider dashboard: {e}")
        pass
    
    # If not authenticated or not provider, still render the page
    # The frontend JavaScript will handle redirect if needed
    return render_template('dashboard_provider.html')


