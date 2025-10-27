from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Feedback, User, Booking, Provider
from datetime import datetime
import os

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin')
@jwt_required()
def admin_dashboard():
    """Admin dashboard for managing feedback and reviews"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user or user.role != 'admin':
            return redirect(url_for('auth.login'))
        
        # Get feedback statistics
        total_feedback = Feedback.objects.count()
        approved_feedback = Feedback.objects(is_approved=True).count()
        pending_feedback = Feedback.objects(is_approved=False).count()
        featured_feedback = Feedback.objects(is_featured=True).count()
        
        # Get recent feedback
        recent_feedback = Feedback.objects().order_by('-created_at').limit(10)
        
        # Get booking statistics
        total_bookings = Booking.objects.count()
        completed_bookings = Booking.objects(status='Completed').count()
        
        # Get provider statistics
        total_providers = Provider.objects.count()
        available_providers = Provider.objects(availability=True).count()
        
        stats = {
            'total_feedback': total_feedback,
            'approved_feedback': approved_feedback,
            'pending_feedback': pending_feedback,
            'featured_feedback': featured_feedback,
            'total_bookings': total_bookings,
            'completed_bookings': completed_bookings,
            'total_providers': total_providers,
            'available_providers': available_providers
        }
        
        return render_template('admin_dashboard.html', 
                             stats=stats, 
                             recent_feedback=recent_feedback)
        
    except Exception as e:
        print(f"Error loading admin dashboard: {str(e)}")
        return redirect(url_for('auth.login'))

@admin_bp.route('/admin/feedback')
@jwt_required()
def admin_feedback():
    """Admin feedback management page"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user or user.role != 'admin':
            return redirect(url_for('auth.login'))
        
        # Get all feedback with pagination
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        feedback_list = Feedback.objects().order_by('-created_at').paginate(
            page=page, per_page=per_page
        )
        
        return render_template('admin_feedback.html', feedback_list=feedback_list)
        
    except Exception as e:
        print(f"Error loading admin feedback: {str(e)}")
        return redirect(url_for('auth.login'))

@admin_bp.route('/api/admin/feedback/<feedback_id>/approve', methods=['POST'])
@jwt_required()
def approve_feedback(feedback_id):
    """Approve feedback for display"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        feedback = Feedback.objects(id=feedback_id).first()
        if not feedback:
            return jsonify({'error': 'Feedback not found'}), 404
        
        feedback.is_approved = True
        feedback.save()
        
        return jsonify({'message': 'Feedback approved successfully'}), 200
        
    except Exception as e:
        print(f"Error approving feedback: {str(e)}")
        return jsonify({'error': 'Failed to approve feedback'}), 500

@admin_bp.route('/api/admin/feedback/<feedback_id>/feature', methods=['POST'])
@jwt_required()
def feature_feedback(feedback_id):
    """Feature feedback on homepage"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        feedback = Feedback.objects(id=feedback_id).first()
        if not feedback:
            return jsonify({'error': 'Feedback not found'}), 404
        
        feedback.is_featured = not feedback.is_featured
        feedback.save()
        
        status = 'featured' if feedback.is_featured else 'unfeatured'
        return jsonify({'message': f'Feedback {status} successfully'}), 200
        
    except Exception as e:
        print(f"Error featuring feedback: {str(e)}")
        return jsonify({'error': 'Failed to feature feedback'}), 500

@admin_bp.route('/api/admin/feedback/<feedback_id>/delete', methods=['DELETE'])
@jwt_required()
def delete_feedback(feedback_id):
    """Delete feedback"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        feedback = Feedback.objects(id=feedback_id).first()
        if not feedback:
            return jsonify({'error': 'Feedback not found'}), 404
        
        feedback.delete()
        
        return jsonify({'message': 'Feedback deleted successfully'}), 200
        
    except Exception as e:
        print(f"Error deleting feedback: {str(e)}")
        return jsonify({'error': 'Failed to delete feedback'}), 500



