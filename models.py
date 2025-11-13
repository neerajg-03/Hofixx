from datetime import datetime
from mongoengine import Document, EmbeddedDocument, fields
from mongoengine import connect, disconnect_all
import os


class SavedAddress(EmbeddedDocument):
    """Embedded document for user's saved addresses"""
    uid = fields.StringField(required=True)
    label = fields.StringField(max_length=100, required=True)
    address = fields.StringField(max_length=255, required=True)
    latitude = fields.FloatField(required=True)
    longitude = fields.FloatField(required=True)
    is_default = fields.BooleanField(default=False)


class User(Document):
    name = fields.StringField(max_length=120, required=True)
    email = fields.EmailField(unique=True)  # Made optional for OTP users
    phone = fields.StringField(max_length=30, unique=True, null=True)  # Made unique for OTP users, null allowed for OAuth
    phone_verified = fields.BooleanField(default=False)
    role = fields.StringField(max_length=20, required=True, choices=['user', 'provider', 'shopkeeper', 'admin'])
    password_hash = fields.StringField(max_length=255)  # Made optional for OAuth/OTP users
    # Optional geolocation and human-readable address
    latitude = fields.FloatField()
    longitude = fields.FloatField()
    address = fields.StringField(max_length=255)
    avatar_path = fields.StringField(max_length=255)
    credits = fields.FloatField(default=0.0)
    rating = fields.FloatField(default=5.0)
    created_at = fields.DateTimeField(default=datetime.utcnow)
    
    # Preferences and settings
    prefers_email_notifications = fields.BooleanField(default=True)
    prefers_sms_notifications = fields.BooleanField(default=False)
    dark_mode = fields.BooleanField(default=False)
    language = fields.StringField(max_length=10, default='en')
    
    # Referral/support
    referral_code = fields.StringField(max_length=20)
    referred_by = fields.StringField(max_length=120)
    referral_bonus_claimed = fields.BooleanField(default=False)
    
    # OAuth fields
    google_id = fields.StringField(max_length=100, unique=True)
    
    # Firebase Authentication fields
    firebase_uid = fields.StringField(max_length=100, unique=True)
    profile_picture = fields.StringField(max_length=500)
    
    # Saved addresses
    saved_addresses = fields.ListField(fields.EmbeddedDocumentField(SavedAddress))

    # Reference to provider profile
    provider_profile = fields.ReferenceField('Provider')
    
    meta = {
        'collection': 'users',
        'indexes': ['email', 'phone', 'role', 'google_id', 'firebase_uid', 'referral_code']
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
    daily_rates = fields.DictField()  # Maps service name to daily rate, e.g., {"Electrician": 2000, "Plumber": 1800}
    
    # Verification fields
    verification_status = fields.StringField(max_length=20, default='pending', 
                                           choices=['pending', 'verified', 'rejected'])
    # Document URLs
    aadhaar_front_url = fields.StringField(max_length=500)
    aadhaar_back_url = fields.StringField(max_length=500)
    pan_url = fields.StringField(max_length=500)
    selfie_url = fields.StringField(max_length=500)
    skill_cert_url = fields.StringField(max_length=500)  # Optional
    police_verification_url = fields.StringField(max_length=500)  # Optional
    
    # GPS location for address verification
    verification_gps_lat = fields.FloatField()
    verification_gps_lon = fields.FloatField()
    verification_address = fields.StringField(max_length=500)
    
    # Admin fields
    admin_remarks = fields.StringField()
    verified_by = fields.ReferenceField('User')  # Admin who verified
    verified_at = fields.DateTimeField()
    rejected_at = fields.DateTimeField()
    
    # Verification timestamps
    verification_submitted_at = fields.DateTimeField()
    verification_updated_at = fields.DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'providers',
        'indexes': ['user', 'availability', 'verification_status']
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
    
    # Booking type and daily rate
    booking_type = fields.StringField(max_length=20, default='hourly', choices=['hourly', 'daily'])
    daily_rate = fields.FloatField()  # Daily rate if booking_type is 'daily'
    
    meta = {
        'collection': 'bookings',
        'indexes': ['user', 'provider', 'service', 'status', 'created_at']
    }


class Payment(Document):
    booking = fields.ReferenceField('Booking')  # Optional, for service bookings
    order = fields.ReferenceField('Order')  # Optional, for shop orders
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
        'indexes': ['booking', 'order', 'user', 'status']
    }


class WalletTransaction(Document):
    """Track wallet transactions for users."""
    user = fields.ReferenceField('User', required=True)
    amount = fields.FloatField(required=True)
    transaction_type = fields.StringField(max_length=10, required=True,
                                          choices=['credit', 'debit'])
    source = fields.StringField(max_length=50, default='topup',
                                choices=['topup', 'admin_bonus', 'referral_bonus',
                                         'service_payment', 'refund', 'purchase', 'wallet_payment'])
    description = fields.StringField()
    balance_after = fields.FloatField()
    external_reference = fields.StringField()
    created_at = fields.DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'wallet_transactions',
        'indexes': ['user', '-created_at', 'source', 'external_reference']
    }


class ReferralRequest(Document):
    """Referral bonus requests awaiting admin approval."""
    user = fields.ReferenceField('User', required=True)
    referrer = fields.ReferenceField('User', required=True)
    referral_code = fields.StringField(required=True)
    bonus_new_user = fields.FloatField(default=0.0)
    bonus_referrer = fields.FloatField(default=0.0)
    status = fields.StringField(max_length=20, default='pending',
                                choices=['pending', 'approved', 'rejected'])
    admin_notes = fields.StringField()
    created_at = fields.DateTimeField(default=datetime.utcnow)
    processed_at = fields.DateTimeField()

    meta = {
        'collection': 'referral_requests',
        'indexes': ['user', 'referrer', 'status', '-created_at']
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
    voice_description_url = fields.StringField()  # URL of uploaded voice description audio file
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


class ShopAd(Document):
    name = fields.StringField(max_length=150, required=True)
    category = fields.StringField(max_length=50, required=True)  # e.g., hardware, electricals, plumbing
    address = fields.StringField(max_length=255)
    contact_phone = fields.StringField(max_length=30)
    contact_email = fields.EmailField()
    website = fields.StringField(max_length=200)
    image_path = fields.StringField(max_length=255)  # stored under static/images/shops
    is_active = fields.BooleanField(default=True)
    priority = fields.IntField(default=0)
    created_at = fields.DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'shop_ads',
        'indexes': ['category', 'is_active', 'priority', '-created_at']
    }


class Shop(Document):
    """Shop model for shopkeepers to register their shops"""
    owner = fields.ReferenceField('User', required=True)  # Shopkeeper user
    name = fields.StringField(max_length=150, required=True)
    description = fields.StringField()
    category = fields.ListField(fields.StringField(max_length=50), required=True)  # List of categories: hardware, electricals, plumbing, etc.
    address = fields.StringField(max_length=255, required=True)
    location_lat = fields.FloatField(required=True)
    location_lon = fields.FloatField(required=True)
    contact_phone = fields.StringField(max_length=30, required=True)
    contact_email = fields.EmailField()
    image_path = fields.StringField(max_length=255)  # Shop logo/image
    is_active = fields.BooleanField(default=True)
    is_verified = fields.BooleanField(default=False)  # Admin verification (deprecated - use verification_status)
    rating = fields.FloatField(default=5.0)
    total_orders = fields.IntField(default=0)
    created_at = fields.DateTimeField(default=datetime.utcnow)
    
    # Shopkeeper verification fields
    verification_status = fields.StringField(max_length=20, default='pending', 
                                           choices=['pending', 'verified', 'rejected'])
    # Document URLs
    shopkeeper_aadhaar_front_url = fields.StringField(max_length=500)
    shopkeeper_aadhaar_back_url = fields.StringField(max_length=500)
    shopkeeper_pan_url = fields.StringField(max_length=500)
    shopkeeper_selfie_url = fields.StringField(max_length=500)
    shop_license_url = fields.StringField(max_length=500)  # Shop license/GST certificate
    police_verification_url = fields.StringField(max_length=500)  # Optional
    
    # GPS location for address verification
    verification_gps_lat = fields.FloatField()
    verification_gps_lon = fields.FloatField()
    verification_address = fields.StringField(max_length=500)
    
    # Admin fields
    admin_remarks = fields.StringField()
    verified_by = fields.ReferenceField('User')  # Admin who verified
    verified_at = fields.DateTimeField()
    rejected_at = fields.DateTimeField()
    
    # Verification timestamps
    verification_submitted_at = fields.DateTimeField()
    verification_updated_at = fields.DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'shops',
        'indexes': ['owner', 'category', 'is_active', 'location_lat', 'location_lon', 'verification_status']
    }


class Product(Document):
    """Product model for items available in shops"""
    shop = fields.ReferenceField('Shop', required=True)
    name = fields.StringField(max_length=200, required=True)
    description = fields.StringField()
    category = fields.StringField(max_length=100, required=True)  # e.g., 'wires', 'pipes', 'tools'
    price = fields.FloatField(required=True)
    stock_quantity = fields.IntField(default=0)
    image_path = fields.StringField(max_length=255)  # Product image
    is_available = fields.BooleanField(default=True)
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'products',
        'indexes': ['shop', 'category', 'name', 'is_available']
    }


class Cart(Document):
    """Shopping cart model for users"""
    user = fields.ReferenceField('User', required=True)
    items = fields.ListField(fields.DictField())  # List of {product_id, shop_id, quantity, price}
    total_amount = fields.FloatField(default=0.0)
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'carts',
        'indexes': ['user']
    }


class Order(Document):
    """Order model for completed purchases"""
    user = fields.ReferenceField('User', required=True)
    shop = fields.ReferenceField('Shop', required=True)
    items = fields.ListField(fields.DictField())  # List of {product_id, product_name, quantity, price}
    total_amount = fields.FloatField(required=True)
    delivery_address = fields.StringField(max_length=255, required=True)
    delivery_lat = fields.FloatField(required=True)
    delivery_lon = fields.FloatField(required=True)
    contact_phone = fields.StringField(max_length=30, required=True)
    
    # Order status
    status = fields.StringField(max_length=30, default='pending',
                               choices=['pending', 'confirmed', 'preparing', 'ready', 'assigned', 'out_for_delivery', 'delivered', 'cancelled'])
    
    # Delivery partner
    delivery_partner = fields.ReferenceField('DeliveryPartner')
    
    # Payment
    payment_status = fields.StringField(max_length=30, default='pending',
                                       choices=['pending', 'paid', 'failed', 'refunded'])
    payment_method = fields.StringField(max_length=30, default='online',
                                       choices=['Cash', 'Card', 'UPI', 'Bank Transfer', 'Razorpay'])
    payment = fields.ReferenceField('Payment')  # Reference to payment if online
    
    # Timing
    created_at = fields.DateTimeField(default=datetime.utcnow)
    confirmed_at = fields.DateTimeField()
    delivered_at = fields.DateTimeField()
    
    meta = {
        'collection': 'orders',
        'indexes': ['user', 'shop', 'status', 'created_at', 'delivery_lat', 'delivery_lon']
    }


class DeliveryPartner(Document):
    """Delivery partner model for delivery personnel"""
    user = fields.ReferenceField('User', required=True, unique=True)
    vehicle_type = fields.StringField(max_length=50, default='bike')  # bike, car, etc.
    vehicle_number = fields.StringField(max_length=20)
    is_available = fields.BooleanField(default=True)
    current_location_lat = fields.FloatField()
    current_location_lon = fields.FloatField()
    rating = fields.FloatField(default=5.0)
    total_deliveries = fields.IntField(default=0)
    created_at = fields.DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'delivery_partners',
        'indexes': ['user', 'is_available', 'current_location_lat', 'current_location_lon']
    }


def connect_to_mongodb():
    """Initialize MongoDB connection"""
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/hofix')
    connect(host=mongodb_uri)


def disconnect_from_mongodb():
    """Disconnect from MongoDB"""
    disconnect_all()
