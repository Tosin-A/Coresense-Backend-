"""
Subscription Router
Endpoints for Stripe Checkout, subscription status, webhook, portal, and cancellation.
Includes lightweight HTML redirect endpoints so Stripe can bounce users back into the app.
"""

import logging
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import stripe

from backend.config import get_settings
from backend.middleware.auth_helper import get_current_user_id
from backend.services import subscription_service
from backend.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/v1/subscription", tags=["subscription"])


def _build_redirect_page(deep_link: str, heading: str, message: str) -> str:
    """Minimal HTML that auto-redirects to a deep link and shows a fallback message."""
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{heading} - CoreSense</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; display: flex;
         justify-content: center; align-items: center; min-height: 100vh;
         margin: 0; background: #0F0F0F; color: #FAFAFA; text-align: center; }}
  .card {{ max-width: 360px; padding: 48px 32px; }}
  h1 {{ font-size: 22px; margin-bottom: 12px; }}
  p {{ font-size: 15px; color: #A1A1AA; line-height: 1.5; margin-bottom: 24px; }}
  a {{ color: #8B5CF6; text-decoration: none; font-weight: 600; }}
</style>
</head><body>
<div class="card">
  <h1>{heading}</h1>
  <p>{message}</p>
  <p><a href="{deep_link}">Tap here to return to CoreSense</a></p>
</div>
<script>window.location.replace("{deep_link}");</script>
</body></html>"""


class CheckoutResponse(BaseModel):
    url: str
    session_id: str


class SubscriptionStatusResponse(BaseModel):
  is_pro: bool
  status: str
  current_period_end: str | None = None
  cancel_at_period_end: bool = False
  source: str | None = None


class PortalResponse(BaseModel):
    url: str


class CancelResponse(BaseModel):
    status: str
    cancel_at_period_end: bool
    current_period_end: str | None = None


class VerifyIAPRequest(BaseModel):
    platform: str
    productId: str
    transactionId: str
    receipt: str | None = None
    purchaseToken: str | None = None


@router.post("/verify-iap", response_model=SubscriptionStatusResponse)
async def verify_iap(
    body: VerifyIAPRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Verify an In-App Purchase and activate Pro subscription."""
    try:
        result = subscription_service.verify_iap_and_activate(
            user_id=user_id,
            platform=body.platform,
            product_id=body.productId,
            transaction_id=body.transactionId,
            receipt=body.receipt,
            purchase_token=body.purchaseToken,
        )
        return SubscriptionStatusResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("IAP verification error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify purchase",
        )


@router.post("/create-checkout", response_model=CheckoutResponse)
async def create_checkout(user_id: str = Depends(get_current_user_id)):
    """Create a Stripe Checkout Session for the Pro subscription."""
    try:
        client = get_supabase_client()
        user_resp = client.auth.admin.get_user_by_id(user_id)
        email = user_resp.user.email if user_resp and user_resp.user else None

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not determine user email",
            )

        result = subscription_service.create_checkout_session(user_id, email)
        return CheckoutResponse(url=result["url"], session_id=result["session_id"])

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except stripe.StripeError as e:
        logger.error("Stripe error creating checkout: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment service error. Please try again.",
        )
    except Exception as e:
        logger.error("Unexpected error creating checkout: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session",
        )


@router.get("/status", response_model=SubscriptionStatusResponse)
async def get_status(user_id: str = Depends(get_current_user_id)):
    """Return the current subscription status for the authenticated user."""
    try:
        result = subscription_service.get_subscription_status(user_id)
        return SubscriptionStatusResponse(**result)
    except Exception as e:
        logger.error("Error fetching subscription status: %s", e, exc_info=True)
        return SubscriptionStatusResponse(
            is_pro=False, status="inactive", cancel_at_period_end=False
        )


@router.post("/portal", response_model=PortalResponse)
async def create_portal(user_id: str = Depends(get_current_user_id)):
    """Create a Stripe Customer Portal session for managing billing."""
    try:
        result = subscription_service.create_customer_portal_session(user_id)
        return PortalResponse(url=result["url"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except stripe.StripeError as e:
        logger.error("Stripe error creating portal: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment service error. Please try again.",
        )
    except Exception as e:
        logger.error("Error creating portal session: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create portal session",
        )


@router.post("/cancel", response_model=CancelResponse)
async def cancel(user_id: str = Depends(get_current_user_id)):
    """Cancel the subscription at the end of the current billing period."""
    try:
        result = subscription_service.cancel_subscription(user_id)
        return CancelResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except stripe.StripeError as e:
        logger.error("Stripe error cancelling subscription: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment service error. Please try again.",
        )
    except Exception as e:
        logger.error("Error cancelling subscription: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel subscription",
        )


@router.get("/redirect/success", response_class=HTMLResponse)
async def redirect_success(session_id: str = ""):
    """After Stripe Checkout, redirect the user back into the app."""
    deep_link = f"coresense://subscription-success?session_id={session_id}"
    return _build_redirect_page(
        deep_link,
        "Payment Successful",
        "Your CoreSense Pro subscription is now active. Redirecting you back to the app\u2026",
    )


@router.get("/redirect/cancel", response_class=HTMLResponse)
async def redirect_cancel():
    """After the user cancels Stripe Checkout, redirect back into the app."""
    return _build_redirect_page(
        "coresense://subscription-cancel",
        "Checkout Cancelled",
        "No worries \u2014 you can upgrade anytime from Settings. Redirecting you back\u2026",
    )


@router.get("/redirect/portal-return", response_class=HTMLResponse)
async def redirect_portal_return():
    """After the user leaves the Stripe Customer Portal, redirect back into the app."""
    return _build_redirect_page(
        "coresense://settings",
        "Returning to CoreSense",
        "Taking you back to the app\u2026",
    )


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.
    Verifies the webhook signature and dispatches to the appropriate handler.
    No auth required -- authenticated via Stripe signature.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )

    if not settings.stripe_webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET is not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured",
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except stripe.SignatureVerificationError:
        logger.warning("Invalid Stripe webhook signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        )
    except Exception as e:
        logger.error("Webhook verification error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook verification failed",
        )

    event_type = event.get("type", "")
    data_object = event.get("data", {}).get("object", {})

    logger.info("Stripe webhook received: %s", event_type)

    try:
        if event_type == "checkout.session.completed":
            subscription_service.handle_checkout_completed(data_object)
        elif event_type == "customer.subscription.updated":
            subscription_service.handle_subscription_updated(data_object)
        elif event_type == "customer.subscription.deleted":
            subscription_service.handle_subscription_deleted(data_object)
        elif event_type == "invoice.payment_failed":
            subscription_service.handle_invoice_payment_failed(data_object)
        else:
            logger.info("Unhandled webhook event type: %s", event_type)
    except Exception as e:
        logger.error("Error processing webhook %s: %s", event_type, e, exc_info=True)

    return {"received": True}
