"""
Subscription Service
Manages Stripe Checkout, webhooks, portal sessions, IAP verification, and subscription lifecycle.
"""

import base64
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone

import httpx
import stripe

from backend.config import get_settings
from backend.database.supabase_client import get_supabase_client
from backend.services.message_limit_service import upgrade_to_pro, downgrade_from_pro

logger = logging.getLogger(__name__)

APPLE_VERIFY_RECEIPT_URL = "https://buy.itunes.apple.com/verifyReceipt"
APPLE_VERIFY_RECEIPT_SANDBOX_URL = "https://sandbox.itunes.apple.com/verifyReceipt"

settings = get_settings()
if settings.stripe_secret_key:
    stripe.api_key = settings.stripe_secret_key

BACKEND_URL = (
    "https://coresense-backend-production.up.railway.app"
    if settings.environment == "production"
    else f"http://localhost:{settings.port}"
)


def _get_subscription_record(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch the subscription row for a user, or None."""
    client = get_supabase_client()
    response = (
        client.table("subscriptions")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


def _upsert_subscription(user_id: str, fields: Dict[str, Any]) -> bool:
    """Insert or update a subscription row for a user."""
    client = get_supabase_client()
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    existing = _get_subscription_record(user_id)
    if existing:
        client.table("subscriptions").update(fields).eq("user_id", user_id).execute()
    else:
        fields["user_id"] = user_id
        client.table("subscriptions").insert(fields).execute()
    return True


def get_or_create_stripe_customer(user_id: str, email: str) -> str:
    """
    Look up or create a Stripe customer for this user.
    Returns the stripe_customer_id.
    """
    record = _get_subscription_record(user_id)
    if record and record.get("stripe_customer_id"):
        return record["stripe_customer_id"]

    customer = stripe.Customer.create(
        email=email,
        metadata={"user_id": user_id},
    )

    _upsert_subscription(user_id, {"stripe_customer_id": customer.id})
    logger.info("Created Stripe customer %s for user %s", customer.id, user_id)
    return customer.id


def create_checkout_session(user_id: str, email: str) -> Dict[str, Any]:
    """
    Create a Stripe Checkout Session in subscription mode.
    Returns {"url": "<checkout_url>", "session_id": "<id>"}.
    """
    if not settings.stripe_secret_key or not settings.stripe_price_id:
        raise ValueError("Stripe is not configured on the server")

    customer_id = get_or_create_stripe_customer(user_id, email)

    redirect_base = f"{BACKEND_URL}/api/v1/subscription/redirect"
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        success_url=f"{redirect_base}/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{redirect_base}/cancel",
        client_reference_id=user_id,
        metadata={"user_id": user_id},
        subscription_data={"metadata": {"user_id": user_id}},
    )

    logger.info("Created checkout session %s for user %s", session.id, user_id)
    return {"url": session.url, "session_id": session.id}


def create_customer_portal_session(user_id: str) -> Dict[str, Any]:
    """
    Create a Stripe Customer Portal session so the user can manage billing.
    Returns {"url": "<portal_url>"}.
    """
    record = _get_subscription_record(user_id)
    if not record or not record.get("stripe_customer_id"):
        raise ValueError("No Stripe customer found for this user")

    session = stripe.billing_portal.Session.create(
        customer=record["stripe_customer_id"],
        return_url=f"{BACKEND_URL}/api/v1/subscription/redirect/portal-return",
    )
    return {"url": session.url}


def get_subscription_status(user_id: str) -> Dict[str, Any]:
    """Return the current subscription status for a user."""
    record = _get_subscription_record(user_id)
    if not record:
        return {
            "is_pro": False,
            "status": "inactive",
            "current_period_end": None,
            "cancel_at_period_end": False,
        }

    is_pro = record.get("status") == "active"
    if is_pro and record.get("current_period_end"):
        try:
            end_dt = datetime.fromisoformat(record["current_period_end"].replace("Z", "+00:00"))
            if end_dt < datetime.now(timezone.utc):
                is_pro = False
        except (ValueError, TypeError):
            pass

    return {
        "is_pro": is_pro,
        "status": record.get("status", "inactive"),
        "current_period_end": record.get("current_period_end"),
        "cancel_at_period_end": record.get("cancel_at_period_end", False),
        "stripe_subscription_id": record.get("stripe_subscription_id"),
        "source": record.get("source", "stripe"),
    }


def cancel_subscription(user_id: str) -> Dict[str, Any]:
    """Cancel the subscription at period end."""
    record = _get_subscription_record(user_id)
    if not record or not record.get("stripe_subscription_id"):
        raise ValueError("No active subscription found")

    sub = stripe.Subscription.modify(
        record["stripe_subscription_id"],
        cancel_at_period_end=True,
    )

    _upsert_subscription(user_id, {"cancel_at_period_end": True})
    logger.info("Scheduled cancellation for user %s", user_id)
    sub_dict = dict(sub)
    period_end = sub_dict.get("current_period_end")
    return {
        "status": sub_dict.get("status", "active"),
        "cancel_at_period_end": True,
        "current_period_end": (
            datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat()
            if period_end
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Webhook handlers
# ---------------------------------------------------------------------------

def handle_checkout_completed(session: Dict[str, Any]) -> None:
    """Process a successful checkout session."""
    user_id = session.get("client_reference_id")
    if not user_id:
        logger.error("checkout.session.completed missing client_reference_id")
        return

    subscription_id = session.get("subscription")
    customer_id = session.get("customer")

    sub = stripe.Subscription.retrieve(subscription_id) if subscription_id else None

    fields: Dict[str, Any] = {
        "stripe_customer_id": customer_id,
        "stripe_subscription_id": subscription_id,
        "status": "active",
    }

    if sub:
        sub_dict = dict(sub)
        items_data = sub_dict.get("items", {}).get("data", [])
        fields["stripe_price_id"] = (
            items_data[0]["price"]["id"] if items_data else None
        )
        period_start = sub_dict.get("current_period_start")
        if period_start:
            fields["current_period_start"] = datetime.fromtimestamp(
                period_start, tz=timezone.utc
            ).isoformat()
        period_end = sub_dict.get("current_period_end")
        if period_end:
            fields["current_period_end"] = datetime.fromtimestamp(
                period_end, tz=timezone.utc
            ).isoformat()
        fields["cancel_at_period_end"] = sub_dict.get("cancel_at_period_end", False)

    _upsert_subscription(user_id, fields)
    upgrade_to_pro(user_id)
    logger.info("Activated pro for user %s via checkout", user_id)


def handle_subscription_updated(subscription: Dict[str, Any]) -> None:
    """Handle subscription status changes (renewals, payment issues, etc.)."""
    user_id = subscription.get("metadata", {}).get("user_id")
    if not user_id:
        customer_id = subscription.get("customer")
        record = _find_by_customer(customer_id)
        if record:
            user_id = record["user_id"]

    if not user_id:
        logger.error("subscription.updated: could not resolve user_id")
        return

    status = subscription.get("status", "inactive")

    fields: Dict[str, Any] = {
        "status": status,
        "cancel_at_period_end": subscription.get("cancel_at_period_end", False),
    }
    if subscription.get("current_period_start"):
        fields["current_period_start"] = datetime.fromtimestamp(
            subscription["current_period_start"], tz=timezone.utc
        ).isoformat()
    if subscription.get("current_period_end"):
        fields["current_period_end"] = datetime.fromtimestamp(
            subscription["current_period_end"], tz=timezone.utc
        ).isoformat()

    _upsert_subscription(user_id, fields)

    if status == "active":
        upgrade_to_pro(user_id)
    elif status in ("canceled", "past_due", "unpaid"):
        downgrade_from_pro(user_id)

    logger.info("Subscription updated for user %s: status=%s", user_id, status)


def handle_subscription_deleted(subscription: Dict[str, Any]) -> None:
    """Handle subscription cancellation / expiry."""
    user_id = subscription.get("metadata", {}).get("user_id")
    if not user_id:
        customer_id = subscription.get("customer")
        record = _find_by_customer(customer_id)
        if record:
            user_id = record["user_id"]

    if not user_id:
        logger.error("subscription.deleted: could not resolve user_id")
        return

    _upsert_subscription(user_id, {
        "status": "canceled",
        "cancel_at_period_end": False,
    })
    downgrade_from_pro(user_id)
    logger.info("Subscription deleted for user %s", user_id)


def handle_invoice_payment_failed(invoice: Dict[str, Any]) -> None:
    """Mark subscription as past_due when payment fails."""
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return

    client = get_supabase_client()
    response = (
        client.table("subscriptions")
        .select("user_id")
        .eq("stripe_subscription_id", subscription_id)
        .limit(1)
        .execute()
    )
    if response.data and len(response.data) > 0:
        user_id = response.data[0]["user_id"]
        _upsert_subscription(user_id, {"status": "past_due"})
        logger.warning("Payment failed for user %s, marking past_due", user_id)


def _find_by_customer(customer_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Look up a subscription record by stripe_customer_id."""
    if not customer_id:
        return None
    client = get_supabase_client()
    response = (
        client.table("subscriptions")
        .select("*")
        .eq("stripe_customer_id", customer_id)
        .limit(1)
        .execute()
    )
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


# ---------------------------------------------------------------------------
# In-App Purchase (Apple / Google)
# ---------------------------------------------------------------------------

def verify_apple_receipt(receipt_b64: str, product_id: str) -> Optional[Dict[str, Any]]:
    """
    Verify Apple receipt with App Store.
    Returns subscription info if valid, None otherwise.
    Also tracks whether the receipt was verified via sandbox.
    """
    secret = settings.apple_shared_secret
    if not secret:
        logger.error("[APPLE_IAP] APPLE_SHARED_SECRET not configured")
        return None

    logger.warning("[APPLE_IAP] Starting verification for product=%s, receipt_length=%d, secret_prefix=%s", product_id, len(receipt_b64), secret[:4] + "...")

    payload = {
        "receipt-data": receipt_b64,
        "password": secret,
        "exclude-old-transactions": True,
    }

    is_sandbox = False
    for url in [APPLE_VERIFY_RECEIPT_URL, APPLE_VERIFY_RECEIPT_SANDBOX_URL]:
        try:
            logger.warning("[APPLE_IAP] POST %s", url)
            resp = httpx.post(url, json=payload, timeout=10)
            data = resp.json()
            status = data.get("status", -1)
            logger.warning("[APPLE_IAP] Response status=%s from %s", status, url)

            if status == 0:
                if url == APPLE_VERIFY_RECEIPT_SANDBOX_URL:
                    is_sandbox = True
                latest = data.get("latest_receipt_info", []) or data.get("receipt", {}).get("in_app", [])
                logger.warning("[APPLE_IAP] Found %d items in receipt, looking for product %s", len(latest), product_id)
                for item in latest:
                    logger.warning("[APPLE_IAP] Receipt item: product_id=%s, expires_date_ms=%s", item.get("product_id"), item.get("expires_date_ms"))
                    if item.get("product_id") == product_id:
                        exp_ms = item.get("expires_date_ms")
                        if exp_ms:
                            exp_dt = datetime.fromtimestamp(int(exp_ms) / 1000, tz=timezone.utc)
                            is_active = exp_dt > datetime.now(timezone.utc)
                            logger.warning("[APPLE_IAP] Product matched: expires_at=%s, is_active=%s, is_sandbox=%s", exp_dt.isoformat(), is_active, is_sandbox)
                            return {
                                "transaction_id": item.get("transaction_id"),
                                "original_transaction_id": item.get("original_transaction_id"),
                                "product_id": product_id,
                                "expires_at": exp_dt.isoformat(),
                                "is_active": is_active,
                                "is_sandbox": is_sandbox,
                            }
                logger.warning("[APPLE_IAP] Product %s not found in receipt items", product_id)
                return None

            if status == 21007:
                logger.warning("[APPLE_IAP] Got 21007 (sandbox receipt), retrying with sandbox URL")
                continue
            logger.warning("[APPLE_IAP] Apple verifyReceipt failed with status=%s", status)
            return None
        except Exception as e:
            logger.error("[APPLE_IAP] Exception during verification: %s", e)
            return None

    logger.warning("[APPLE_IAP] Both production and sandbox URLs failed")
    return None


def verify_iap_and_activate(user_id: str, platform: str, product_id: str, transaction_id: str, receipt: Optional[str] = None, purchase_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Verify IAP purchase and activate Pro for the user.
    Returns subscription status dict.
    """
    if platform == "ios" and receipt:
        sub_info = verify_apple_receipt(receipt, product_id)
        if not sub_info:
            raise ValueError("Invalid Apple receipt - could not verify with App Store")

        # Sandbox subscriptions expire in minutes, so accept them even if expired
        # Production subscriptions must be active
        is_sandbox = sub_info.get("is_sandbox", False)
        is_active = sub_info.get("is_active", False)

        if not is_active and not is_sandbox:
            raise ValueError("Apple subscription has expired")

        if is_sandbox and not is_active:
            logger.warning("[APPLE_IAP] Accepting expired sandbox receipt for user %s (sandbox testing)", user_id)

        # For sandbox receipts, set a far-future expiry so status checks don't deactivate Pro
        expires_at = sub_info.get("expires_at")
        if is_sandbox and not is_active:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()

        _upsert_subscription(user_id, {
            "source": "apple",
            "status": "active",
            "apple_subscription_id": sub_info.get("original_transaction_id"),
            "apple_transaction_id": sub_info.get("transaction_id"),
            "apple_original_transaction_id": sub_info.get("original_transaction_id"),
            "current_period_end": expires_at,
            "cancel_at_period_end": False,
        })
        upgrade_to_pro(user_id)
        logger.info("Activated Pro for user %s via Apple IAP", user_id)
        return get_subscription_status(user_id)

    if platform == "android" and purchase_token:
        raise ValueError("Google Play verification not implemented yet")

    raise ValueError("Invalid IAP payload: need receipt (iOS) or purchaseToken (Android)")
