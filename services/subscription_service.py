"""
Subscription Service
Manages Stripe Checkout, webhooks, portal sessions, and subscription lifecycle.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

import stripe

from backend.config import get_settings
from backend.database.supabase_client import get_supabase_client
from backend.services.message_limit_service import upgrade_to_pro, downgrade_from_pro

logger = logging.getLogger(__name__)

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

    return {
        "is_pro": record.get("status") == "active",
        "status": record.get("status", "inactive"),
        "current_period_end": record.get("current_period_end"),
        "cancel_at_period_end": record.get("cancel_at_period_end", False),
        "stripe_subscription_id": record.get("stripe_subscription_id"),
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
