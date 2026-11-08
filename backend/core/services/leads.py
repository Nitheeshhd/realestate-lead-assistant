import re
import secrets

from django.utils import timezone

from core.models import Lead


def normalize_phone(raw: str) -> str:
    """Return the last 10 digits of an Indian mobile number, or raise ValueError."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise ValueError("Enter a valid 10-digit Indian mobile number.")
    return digits


def find_primary(phone_norm: str):
    return (Lead.objects.filter(phone_norm=phone_norm, duplicate_of__isnull=True)
            .order_by("created_at").first())


def create_lead(*, name, phone, source, project, wants="", budget="", language="en",
                consent=False, created_at=None):
    """Create a lead. A second enquiry from the same number is stored but flagged as a
    duplicate of the first, so source attribution is kept and counts are not inflated."""
    phone_norm = normalize_phone(phone)
    primary = find_primary(phone_norm)
    lead = Lead.objects.create(
        name=name.strip(), phone=phone.strip(), phone_norm=phone_norm, source=source,
        project=project, wants=wants, budget=budget, language=language, consent=consent,
        duplicate_of=primary, chat_token=secrets.token_urlsafe(24),
        created_at=created_at or timezone.now())
    return lead, primary
