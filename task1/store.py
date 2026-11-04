"""In-memory fixture store for Task 1 business behavior."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from uuid import uuid4


_CUSTOMERS: dict[str, dict[str, str]] = {
    "CUST-12345": {
        "customer_id": "CUST-12345",
        "name": "Avery Morgan",
        "email": "avery.morgan@example.test",
        "plan": "enterprise",
        "balance": "150.00",
    },
    "CUST-23456": {
        "customer_id": "CUST-23456",
        "name": "Jordan Lee",
        "email": "jordan.lee@example.test",
        "plan": "standard",
        "balance": "50.00",
    },
    "CUST-34567": {
        "customer_id": "CUST-34567",
        "name": "Riley Patel",
        "email": "riley.patel@example.test",
        "plan": "starter",
        "balance": "25.00",
    },
}

_REFUNDS: list[dict[str, str]] = []


def get(customer_id: str) -> dict[str, str] | None:
    """Return a defensive copy so callers cannot mutate fixture state directly."""
    customer = _CUSTOMERS.get(customer_id)
    return deepcopy(customer) if customer is not None else None


def record_refund(customer_id: str, amount: float, reason: str) -> dict[str, str]:
    """Record a refund and reduce the customer's remaining refundable balance."""
    customer = _CUSTOMERS[customer_id]
    current_balance = Decimal(customer["balance"])
    refund_amount = Decimal(str(amount))
    remaining_balance = current_balance - refund_amount
    customer["balance"] = f"{remaining_balance:.2f}"

    refund = {
        "refund_id": f"RFND-{uuid4().hex[:12].upper()}",
        "customer_id": customer_id,
        "amount": f"{refund_amount:.2f}",
        "reason": reason,
    }
    _REFUNDS.append(refund)
    return deepcopy(refund)
