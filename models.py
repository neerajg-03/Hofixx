from datetime import datetime
from mongoengine import Document, EmbeddedDocument, fields
from mongoengine import connect, disconnect_all
import os


class User(Document):
    name = fields.StringField(max_length=120, required=True)
    email = fields.EmailField(unique=True)  # Made optional for OTP users
    phone = fields.StringField(max_length=30, unique=True, sparse=True, null=True)
    role = fields.StringField(max_length=20, required=True, choices=['user', 'provider', 'admin'])
    password_hash = fields.StringField(max_length=255)  # Made optional for OAuth/OTP users
    # Optional geolocation and human-readable address
    latitude = fields.FloatField()
    longitude = fields.FloatField()
    address = fields.StringField(max_length=255)
    avatar_path = fields.StringField(max_length=255)
    credits = fields.FloatField(default=0.0)
    rating = fields.FloatField(default=5.0)
    created_at = fields.DateTimeField(default=datetime.utcnow)
    
    # OAuth fields
    google_id = fields.StringField(max_length=100, unique=True)
    
    # Firebase Authentication fields
    firebase_uid = fields.StringField(max_length=100, unique=True)
    profile_picture = fields.StringField(max_length=500)
    
    # Reference to provider profile
    provider_profile = fields.ReferenceField('Provider')
    
    meta = {
        'collection': 'users',
        'indexes': ['email', 'phone', 'role', 'google_id', 'firebase_uid']
    }


class Service(Document):
    name = fields.StringField(max_length=100, required=True)
    category = fields.StringField(max_length=100, required=True)
    base_price = fields.FloatField(required=True)
    image_path = fields.StringField(max_length=255)
    location_lat = fields.FloatField()
    location_lon = fields.FloatField()
    
    meta = {
        'collection': 'services',
        'indexes': ['category', 'name']
    }


class Provider(Document):
    user = fields.ReferenceField('User', required=True, unique=True)
    skills = fields.ListField(fields.StringField())  # List of skills instead of comma-separated
    availability = fields.BooleanField(default=True)
    
    meta = {
        'collection': 'providers',
        'indexes': ['user', 'availability']
    }


class Booking(Document):
    user = fields.ReferenceField('User', required=True)
    provider = fields.ReferenceField('Provider')
    service = fields.ReferenceField('Service', required=True)
    status = fields.StringField(max_length=50, default='Pending', 
                               choices=['Pending', 'Accepted', 'Rejected', 'In Progress', 'Completed', 'Cancelled'])
    scheduled_time = fields.DateTimeField()
    price = fields.FloatField(default=0.0)
    location_lat = fields.FloatField()
    location_lon = fields.FloatField()
    notes = fields.StringField()
    rating = fields.FloatField()  # Optional user rating for the completed booking
    review = fields.StringField()  # Optional user review text
    created_at = fields.DateTimeField(default=datetime.utcnow)
    
    # Service details for easier access
    service_name = fields.StringField(max_length=100)
    provider_id = fields.StringField()
    provider_name = fields.StringField(max_length=100)
    
    # Payment status
    has_payment = fields.BooleanField(default=False)
    payment_status = fields.StringField(max_length=30, default='Pending')
    
    # Service completion details
    completion_notes = fields.StringField()  # Provider's completion notes
    completion_images = fields.ListField(fields.StringField())  # URLs of completion images
    completed_at = fields.DateTimeField()  # When service was completed
    
    # Reference to payment
    payment = fields.ReferenceField('Payment')
    
    meta = {
        'collection': 'bookings',
        'indexes': ['user', 'provider', 'service', 'status', 'created_at']
    }


class Payment(Document):
    booking = fields.ReferenceField('Booking', required=True, unique=True)
    user = fields.ReferenceField('User', required=True)
    amount = fields.FloatField(required=True)
    currency = fields.StringField(max_length=10, default='INR')
    method = fields.StringField(max_length=30, required=True, 
                               choices=['Cash', 'Card', 'UPI', 'Bank Transfer', 'Razorpay'])
    status = fields.StringField(max_length=30, default='Pending',
                               choices=['Success', 'Failed', 'Pending', 'Refunded'])
    created_at = fields.DateTimeField(default=datetime.utcnow)
    
    # Razorpay specific fields
    razorpay_payment_id = fields.StringField()
    razorpay_order_id = fields.StringField()
    razorpay_signature = fields.StringField()
    
    meta = {
        'collection': 'payments',
        'indexes': ['booking', 'user', 'status']
    }


class ServiceCompletion(Document):
    """Model for tracking service completion uploads"""
    booking = fields.ReferenceField('Booking', required=True, unique=True)
    provider = fields.ReferenceField('Provider', required=True)
    completion_notes = fields.StringField()
    images = fields.ListField(fields.StringField())  # URLs of uploaded images
    completed_at = fields.DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'service_completions',
        'indexes': ['booking', 'provider', 'completed_at']
    }




class ServiceRequest(Document):
    """Model for service requests that providers can bid on"""
    user = fields.ReferenceField('User', required=True)
    service_category = fields.StringField(max_length=100, required=True)  # e.g., 'plumber', 'electrician'
    title = fields.StringField(max_length=200, required=True)
    description = fields.StringField(required=True)
    images = fields.ListField(fields.StringField())  # URLs of uploaded images
    location_lat = fields.FloatField(required=True)
    location_lon = fields.FloatField(required=True)
    location_address = fields.StringField(max_length=255, required=True)
    
    # Request details
    urgency = fields.StringField(max_length=20, default='normal', 
                                choices=['emergency', 'urgent', 'normal', 'flexible'])
    preferred_date = fields.DateTimeField()
    preferred_time_slot = fields.StringField(max_length=50)  # e.g., 'morning', 'afternoon', 'evening'
    
    # Status tracking
    status = fields.StringField(max_length=30, default='open', 
                               choices=['open', 'quotes_received', 'quote_selected', 'in_progress', 'completed', 'cancelled'])
    selected_quote = fields.ReferenceField('ProviderQuote')
    
    # Timing
    created_at = fields.DateTimeField(default=datetime.utcnow)
    quote_deadline = fields.DateTimeField()  # When quotes should be submitted by
    expires_at = fields.DateTimeField()  # When the request expires
    
    # Final booking details (after quote selection)
    final_booking = fields.ReferenceField('Booking')
    
    meta = {
        'collection': 'service_requests',
        'indexes': ['user', 'service_category', 'status', 'created_at', 'location_lat', 'location_lon']
    }


class ProviderQuote(Document):
    """Model for provider quotes on service requests"""
    service_request = fields.ReferenceField('ServiceRequest', required=True)
    provider = fields.ReferenceField('Provider', required=True)
    
    # Quote details
    price = fields.FloatField(required=True)
    currency = fields.StringField(max_length=10, default='INR')
    estimated_duration = fields.StringField(max_length=100)  # e.g., '2-3 hours', '1 day'
    quote_notes = fields.StringField()  # Provider's additional notes
    quote_images = fields.ListField(fields.StringField())  # Optional images from provider
    
    # Status
    status = fields.StringField(max_length=30, default='submitted', 
                               choices=['submitted', 'selected', 'rejected', 'expired', 'cancelled'])
    
    # Timing
    submitted_at = fields.DateTimeField(default=datetime.utcnow)
    expires_at = fields.DateTimeField()  # When this quote expires
    
    # Additional fields for easier querying
    provider_name = fields.StringField(max_length=100)
    provider_rating = fields.FloatField()
    provider_phone = fields.StringField()
    
    meta = {
        'collection': 'provider_quotes',
        'indexes': ['service_request', 'provider', 'status', 'submitted_at']
    }


class ProviderNotification(Document):
    """Model for notifying providers about new service requests"""
    provider = fields.ReferenceField('Provider', required=True)
    service_request = fields.ReferenceField('ServiceRequest', required=True)
    
    # Notification details
    notification_type = fields.StringField(max_length=50, default='new_request',
                                         choices=['new_request', 'quote_selected', 'quote_rejected', 'request_cancelled', 'quote_cancelled'])
    title = fields.StringField(max_length=200, required=True)
    message = fields.StringField(required=True)
    
    # Status
    is_read = fields.BooleanField(default=False)
    is_sent = fields.BooleanField(default=False)
    
    # Timing
    created_at = fields.DateTimeField(default=datetime.utcnow)
    read_at = fields.DateTimeField()
    
    meta = {
        'collection': 'provider_notifications',
        'indexes': ['provider', 'is_read', 'created_at']
    }


class Feedback(Document):
    user = fields.ReferenceField('User', required=True)
    name = fields.StringField(max_length=100, required=True)
    email = fields.EmailField(required=True)
    rating = fields.IntField(required=True, min_value=1, max_value=5)
    title = fields.StringField(max_length=200, required=True)
    message = fields.StringField(max_length=1000, required=True)
    is_featured = fields.BooleanField(default=False)  # For displaying on homepage
    is_approved = fields.BooleanField(default=False)  # Admin approval
    created_at = fields.DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'feedback',
        'indexes': ['user', 'rating', 'is_featured', 'is_approved', 'created_at']
    }


def connect_to_mongodb():
    """Initialize MongoDB connection"""
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/hofix')
    connect(host=mongodb_uri)


def disconnect_from_mongodb():
    """Disconnect from MongoDB"""
    disconnect_all()
