from datetime import datetime
from bson import ObjectId
from models import User, WalletTransaction, ReferralRequest


class WalletError(Exception):
    """Custom exception for wallet operations."""


def resolve_user(ident):
    """Fetch a user document using a JWT identity payload."""
    if ident is None:
        return None

    if isinstance(ident, dict):
        user_id = ident.get('id') or ident.get('user_id') or ident
    else:
        user_id = ident

    try:
        return User.objects(id=ObjectId(str(user_id))).first()
    except Exception:
        return User.objects(id=str(user_id)).first()


def record_transaction(user, amount, transaction_type='credit', source='topup', description='', external_reference=None):
    """Adjust wallet balance and create a transaction record."""
    if amount <= 0:
        raise WalletError('Amount must be greater than zero')

    if transaction_type not in ['credit', 'debit']:
        raise WalletError('Invalid transaction type')

    if user is None:
        raise WalletError('User not found')

    if external_reference:
        existing = WalletTransaction.objects(external_reference=external_reference).first()
        if existing:
            raise WalletError('Transaction already processed')

    user.reload()
    current_balance = float(user.credits or 0.0)

    if transaction_type == 'credit':
        new_balance = current_balance + float(amount)
    else:
        if current_balance < amount:
            raise WalletError('Insufficient wallet balance')
        new_balance = current_balance - float(amount)

    user.credits = round(new_balance, 2)
    user.save()

    WalletTransaction(
        user=user,
        amount=round(float(amount), 2),
        transaction_type=transaction_type,
        source=source,
        description=description,
        balance_after=user.credits,
        external_reference=external_reference,
        created_at=datetime.utcnow()
    ).save()

    return user.credits


def get_wallet_summary(user, limit=20):
    """Return wallet balance and recent transactions."""
    if not user:
        raise WalletError('User not found')

    if not user.referral_code:
        try:
            generated_code = f"HX{str(user.id)[-6:]}".upper()
            user.referral_code = generated_code
            user.save()
        except Exception:
            pass

    pending_request = ReferralRequest.objects(user=user, status='pending').first()

    transactions = WalletTransaction.objects(user=user).order_by('-created_at').limit(limit)
    summary = {
        'credits': round(float(user.credits or 0.0), 2),
        'referral_code': user.referral_code,
        'referral_bonus_claimed': bool(user.referral_bonus_claimed),
        'referred_by': user.referred_by,
        'pending_referral': {
            'id': str(pending_request.id),
            'referral_code': pending_request.referral_code,
            'created_at': pending_request.created_at.isoformat()
        } if pending_request else None,
        'transactions': [{
            'id': str(tx.id),
            'amount': tx.amount,
            'transaction_type': tx.transaction_type,
            'source': tx.source,
            'description': tx.description,
            'balance_after': tx.balance_after,
            'created_at': tx.created_at.isoformat() if tx.created_at else None,
            'external_reference': tx.external_reference
        } for tx in transactions]
    }
    return summary

