from datetime import datetime
from bson import ObjectId
from models import Provider, ProviderDepositTransaction, Booking


class ProviderDepositError(Exception):
    """Custom exception for provider deposit operations."""


def resolve_provider(ident):
    """Fetch a provider document using a JWT identity payload."""
    from models import User
    if ident is None:
        return None

    if isinstance(ident, dict):
        user_id = ident.get('id') or ident.get('user_id') or ident
    else:
        user_id = ident

    try:
        user = User.objects(id=ObjectId(str(user_id))).first()
    except Exception:
        user = User.objects(id=str(user_id)).first()
    
    if not user:
        return None
    
    return Provider.objects(user=user).first()


def record_deposit_transaction(provider, amount, transaction_type='credit', source='recharge', 
                               description='', booking=None, commission_rate=None, 
                               commission_amount=None, external_reference=None):
    """Adjust provider deposit balance and create a transaction record."""
    if amount <= 0:
        raise ProviderDepositError('Amount must be greater than zero')

    if transaction_type not in ['credit', 'debit']:
        raise ProviderDepositError('Invalid transaction type')

    if provider is None:
        raise ProviderDepositError('Provider not found')

    if external_reference:
        existing = ProviderDepositTransaction.objects(external_reference=external_reference).first()
        if existing:
            raise ProviderDepositError('Transaction already processed')

    provider.reload()
    current_balance = float(provider.deposit_balance or 0.0)

    if transaction_type == 'credit':
        new_balance = current_balance + float(amount)
    else:
        if current_balance < amount:
            raise ProviderDepositError('Insufficient deposit balance')
        new_balance = current_balance - float(amount)

    provider.deposit_balance = round(new_balance, 2)
    provider.save()

    ProviderDepositTransaction(
        provider=provider,
        amount=round(float(amount), 2),
        transaction_type=transaction_type,
        source=source,
        description=description,
        balance_after=provider.deposit_balance,
        booking=booking,
        commission_rate=commission_rate,
        commission_amount=commission_amount,
        external_reference=external_reference,
        created_at=datetime.utcnow()
    ).save()

    return provider.deposit_balance


def deduct_commission(provider, booking, commission_rate=10.0):
    """Deduct Hofix commission from provider's deposit when they receive cash payment."""
    if not provider:
        raise ProviderDepositError('Provider not found')
    
    if not booking:
        raise ProviderDepositError('Booking not found')
    
    # Calculate commission amount (default 10% of booking price)
    booking_price = float(booking.price or 0)
    if booking_price <= 0:
        raise ProviderDepositError('Invalid booking price')
    
    commission_amount = round(booking_price * (commission_rate / 100), 2)
    
    if commission_amount <= 0:
        raise ProviderDepositError('Commission amount must be greater than zero')
    
    # Check if provider has sufficient balance
    provider.reload()
    current_balance = float(provider.deposit_balance or 0.0)
    
    if current_balance < commission_amount:
        raise ProviderDepositError(f'Insufficient deposit balance. Required: ₹{commission_amount:.2f}, Available: ₹{current_balance:.2f}')
    
    # Deduct commission
    description = f'Hofix commission ({commission_rate}%) for booking {booking.service_name or "Service"} (ID: {booking.id})'
    new_balance = record_deposit_transaction(
        provider=provider,
        amount=commission_amount,
        transaction_type='debit',
        source='commission_deduction',
        description=description,
        booking=booking,
        commission_rate=commission_rate,
        commission_amount=commission_amount
    )
    
    return {
        'commission_amount': commission_amount,
        'commission_rate': commission_rate,
        'booking_price': booking_price,
        'new_balance': new_balance
    }


def check_minimum_balance(provider, minimum_balance=500.0):
    """Check if provider has minimum required balance (default ₹500)."""
    if not provider:
        return False, 'Provider not found'
    
    provider.reload()
    current_balance = float(provider.deposit_balance or 0.0)
    
    if current_balance < minimum_balance:
        return False, f'Minimum deposit balance of ₹{minimum_balance:.2f} required. Current balance: ₹{current_balance:.2f}'
    
    return True, None


def get_deposit_summary(provider, limit=20):
    """Return deposit balance and recent transactions."""
    if not provider:
        raise ProviderDepositError('Provider not found')

    provider.reload()
    transactions = ProviderDepositTransaction.objects(provider=provider).order_by('-created_at').limit(limit)
    
    summary = {
        'deposit_balance': round(float(provider.deposit_balance or 0.0), 2),
        'minimum_required': 500.0,
        'is_eligible': float(provider.deposit_balance or 0.0) >= 500.0,
        'transactions': [{
            'id': str(tx.id),
            'amount': tx.amount,
            'transaction_type': tx.transaction_type,
            'source': tx.source,
            'description': tx.description,
            'balance_after': tx.balance_after,
            'booking_id': str(tx.booking.id) if tx.booking else None,
            'commission_rate': tx.commission_rate,
            'commission_amount': tx.commission_amount,
            'created_at': tx.created_at.isoformat() if tx.created_at else None,
            'external_reference': tx.external_reference
        } for tx in transactions]
    }
    return summary

