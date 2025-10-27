from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Feedback, User
from datetime import datetime
import os

feedback_bp = Blueprint('feedback', __name__)

@feedback_bp.route('/api/feedback/submit', methods=['POST'])
@jwt_required()
def submit_feedback():
    """Submit user feedback"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'email', 'rating', 'title', 'message']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'{field} is required'}), 400
        
        # Validate rating
        rating = int(data['rating'])
        if rating < 1 or rating > 5:
            return jsonify({'error': 'Rating must be between 1 and 5'}), 400
        
        # Create feedback
        feedback = Feedback(
            user=user,
            name=data['name'],
            email=data['email'],
            rating=rating,
            title=data['title'],
            message=data['message'],
            is_approved=False,  # Requires admin approval
            is_featured=False
        )
        
        feedback.save()
        
        return jsonify({
            'message': 'Feedback submitted successfully! Thank you for your review.',
            'feedback_id': str(feedback.id)
        }), 201
        
    except Exception as e:
        print(f"Error submitting feedback: {str(e)}")
        return jsonify({'error': 'Failed to submit feedback'}), 500

@feedback_bp.route('/api/feedback/featured', methods=['GET'])
def get_featured_feedback():
    """Get featured feedback for homepage display"""
    try:
        # Get approved and featured feedback, ordered by rating and date
        feedback_list = Feedback.objects(
            is_approved=True,
            is_featured=True
        ).order_by('-rating', '-created_at').limit(6)
        
        feedback_data = []
        for feedback in feedback_list:
            feedback_data.append({
                'id': str(feedback.id),
                'name': feedback.name,
                'rating': feedback.rating,
                'title': feedback.title,
                'message': feedback.message,
                'created_at': feedback.created_at.strftime('%B %Y')
            })
        
        return jsonify({
            'feedback': feedback_data,
            'count': len(feedback_data)
        }), 200
        
    except Exception as e:
        print(f"Error fetching featured feedback: {str(e)}")
        return jsonify({'error': 'Failed to fetch feedback'}), 500

@feedback_bp.route('/api/feedback/user', methods=['GET'])
@jwt_required()
def get_user_feedback():
    """Get feedback submitted by current user"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get user's feedback
        feedback_list = Feedback.objects(user=user).order_by('-created_at')
        
        feedback_data = []
        for feedback in feedback_list:
            feedback_data.append({
                'id': str(feedback.id),
                'name': feedback.name,
                'rating': feedback.rating,
                'title': feedback.title,
                'message': feedback.message,
                'is_approved': feedback.is_approved,
                'is_featured': feedback.is_featured,
                'created_at': feedback.created_at.strftime('%B %d, %Y')
            })
        
        return jsonify({
            'feedback': feedback_data,
            'count': len(feedback_data)
        }), 200
        
    except Exception as e:
        print(f"Error fetching user feedback: {str(e)}")
        return jsonify({'error': 'Failed to fetch user feedback'}), 500

@feedback_bp.route('/api/feedback/stats', methods=['GET'])
def get_feedback_stats():
    """Get feedback statistics for homepage"""
    try:
        # Get total feedback count
        total_feedback = Feedback.objects(is_approved=True).count()
        
        # Get average rating
        approved_feedback = Feedback.objects(is_approved=True)
        if approved_feedback.count() > 0:
            total_rating = sum(f.rating for f in approved_feedback)
            average_rating = round(total_rating / approved_feedback.count(), 1)
        else:
            average_rating = 0
        
        # Get rating distribution
        rating_distribution = {}
        for i in range(1, 6):
            rating_distribution[str(i)] = approved_feedback.filter(rating=i).count()
        
        return jsonify({
            'total_feedback': total_feedback,
            'average_rating': average_rating,
            'rating_distribution': rating_distribution
        }), 200
        
    except Exception as e:
        print(f"Error fetching feedback stats: {str(e)}")
        return jsonify({'error': 'Failed to fetch feedback statistics'}), 500



