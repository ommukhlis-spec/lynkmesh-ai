"""
Sample project entry point — demonstrates the full module dependency chain.

Usage:
    python main.py

This exercises all modules:
    main → payment → auth → models
    main → payment → auth → utils
    main → notifications → models
    main → notifications → utils
"""

from auth.service import AuthService, AuthError
from payment.processor import PaymentProcessor, PaymentError
from notifications.sender import NotificationSender, Notification, NotificationChannel
from models.user import UserRole


def main() -> None:
    """Run a demonstration of the sample project's functionality."""

    print("=" * 60)
    print("  Sample Project — LynkMesh AI Demo")
    print("=" * 60)

    # 1. Set up auth service
    auth = AuthService()
    print("\n[1] Registering users...")

    admin = auth.register("admin@example.com", "admin_user", "securePass1", role=UserRole.ADMIN)
    print(f"    Admin created: {admin.id}")

    alice = auth.register("alice@example.com", "alice_j", "securePass1")
    print(f"    Alice created: {alice.id}")

    bob = auth.register("bob@example.com", "bob_smith", "securePass1")
    print(f"    Bob created: {bob.id}")

    # 2. Login
    print("\n[2] Authenticating...")
    admin_token, _ = auth.login("admin@example.com", "securePass1")
    alice_token, _ = auth.login("alice@example.com", "securePass1")
    print(f"    Admin token: {admin_token[:16]}...")
    print(f"    Alice token: {alice_token[:16]}...")

    # 3. Process a payment (payment → auth → models + utils)
    print("\n[3] Processing payment...")
    processor = PaymentProcessor(auth)
    try:
        result = processor.process_payment(
            auth_token=alice_token,
            payer_id=alice.id,
            payee_id=bob.id,
            amount_cents=5000,  # $50.00
            currency="USD",
            description="Dinner reimbursement",
        )
        print(f"    Transaction: {result.transaction_id}")
        print(f"    Status: {result.status.value}")
    except PaymentError as e:
        print(f"    Payment failed: {e}")

    # 4. Send a notification (notifications → models + utils)
    print("\n[4] Sending notification...")
    sender = NotificationSender()

    # Register a mock email transport
    def mock_email_handler(notif: Notification, user):
        print(f"    [MOCK EMAIL] To: {user.email}")
        print(f"    [MOCK EMAIL] Subject: {notif.subject}")
        return True

    sender.register_transport(NotificationChannel.EMAIL, mock_email_handler)

    notif = Notification(
        user_id=alice.id,
        channel=NotificationChannel.EMAIL,
        subject="Payment Confirmed",
        body=f"Your payment of $50.00 to {bob.username} has been processed.",
    )
    sent = sender.send(notif, alice)
    print(f"    Sent: {sent}")

    # 5. Verify auth
    print("\n[5] Verifying authorization...")
    try:
        auth.authorize(alice_token, UserRole.ADMIN)
    except Exception as e:
        print(f"    Alice cannot access admin: {e}")

    auth.authorize(admin_token, UserRole.ADMIN)
    print("    Admin authorized successfully")

    print("\n" + "=" * 60)
    print("  Demo complete. All modules exercised.")
    print("=" * 60)


if __name__ == "__main__":
    main()
