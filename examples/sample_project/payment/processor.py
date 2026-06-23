"""
Payment processor — handles transactions, validation, and settlement.

Depends on:
- models.user (User)
- auth.service (AuthService, UnauthorizedError)
- utils.validators (sanitize_input)

Creates a multi-level dependency chain:
  payment → auth → models
  payment → auth → utils
  payment → utils
  payment → models
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from models.user import User
from auth.service import AuthService, UnauthorizedError
from utils.validators import sanitize_input


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentError(Exception):
    """Base exception for payment failures."""


class InsufficientFundsError(PaymentError):
    """Raised when the source account has insufficient funds."""


class PaymentMethodInvalidError(PaymentError):
    """Raised when the payment method is invalid or expired."""


@dataclass
class PaymentResult:
    """Result of a payment operation."""

    transaction_id: str
    status: PaymentStatus
    amount_cents: int
    currency: str
    payer_id: str
    payee_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def is_successful(self) -> bool:
        return self.status == PaymentStatus.COMPLETED


class PaymentProcessor:
    """
    Processes payments with auth integration.

    Requires:
    - AuthService for role verification
    - User models for payer/payee identity
    """

    SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CAD"}

    def __init__(self, auth_service: AuthService) -> None:
        self.auth_service = auth_service
        self._transactions: dict[str, PaymentResult] = {}

    def process_payment(
        self,
        auth_token: str,
        payer_id: str,
        payee_id: str,
        amount_cents: int,
        currency: str = "USD",
        description: str = "",
    ) -> PaymentResult:
        """
        Process a payment from payer to payee.

        Args:
            auth_token: Valid auth token for the payer.
            payer_id: User ID of the payer.
            payee_id: User ID of the payee.
            amount_cents: Payment amount in cents.
            currency: ISO 4217 currency code.
            description: Payment description.

        Returns:
            PaymentResult with transaction details.

        Raises:
            PaymentError: If payment cannot be processed.
        """
        # Authorize
        user = self.auth_service.authorize(auth_token, __import__("models.user").UserRole.USER)

        if user.id != payer_id:
            raise UnauthorizedError("Token does not match payer identity")

        # Validate inputs
        if amount_cents <= 0:
            raise PaymentError("Amount must be positive")
        if currency.upper() not in self.SUPPORTED_CURRENCIES:
            raise PaymentError(f"Unsupported currency: {currency}")
        if payer_id == payee_id:
            raise PaymentError("Payer and payee cannot be the same")

        description = sanitize_input(description, max_length=256)

        # Verify payee exists
        payee = self.auth_service.get_user(payee_id)
        if not payee:
            raise PaymentError(f"Payee not found: {payee_id}")

        # Generate transaction
        transaction_id = f"txn_{uuid.uuid4().hex[:16]}"
        result = PaymentResult(
            transaction_id=transaction_id,
            status=PaymentStatus.PROCESSING,
            amount_cents=amount_cents,
            currency=currency.upper(),
            payer_id=payer_id,
            payee_id=payee_id,
        )

        # Simulate processing
        try:
            self._execute_transfer(payer_id, payee_id, amount_cents)
            result.status = PaymentStatus.COMPLETED
            result.completed_at = datetime.now(timezone.utc)
        except PaymentError as exc:
            result.status = PaymentStatus.FAILED
            result.error_message = str(exc)
            raise

        self._transactions[transaction_id] = result
        return result

    def get_transaction(self, transaction_id: str) -> Optional[PaymentResult]:
        """Retrieve a transaction by ID."""
        return self._transactions.get(transaction_id)

    def refund(self, auth_token: str, transaction_id: str) -> PaymentResult:
        """
        Refund a completed payment (admin only).

        Args:
            auth_token: Admin auth token.
            transaction_id: The transaction to refund.

        Returns:
            Updated PaymentResult with refund status.
        """
        self.auth_service.authorize(
            auth_token, __import__("models.user").UserRole.ADMIN
        )

        original = self._transactions.get(transaction_id)
        if not original:
            raise PaymentError(f"Transaction not found: {transaction_id}")
        if original.status != PaymentStatus.COMPLETED:
            raise PaymentError("Only completed transactions can be refunded")
        if original.status == PaymentStatus.REFUNDED:
            raise PaymentError("Transaction already refunded")

        original.status = PaymentStatus.REFUNDED
        original.error_message = "Refunded"
        return original

    def _execute_transfer(self, source_id: str, dest_id: str, amount_cents: int) -> None:
        """Simulate a funds transfer (would integrate with payment gateway)."""
        # Simulated: would call external payment API here
        if amount_cents > 1_000_000_00:  # $1M cap in cents
            raise InsufficientFundsError("Amount exceeds transaction limit")
