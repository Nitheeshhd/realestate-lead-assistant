from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import Lead, Profile, Project, VisitSlot


def make_world():
    User = get_user_model()
    head = User.objects.create_user("head", password="pw-test-123")
    Profile.objects.create(user=head, role="sales_head")
    exe = User.objects.create_user("exe", password="pw-test-123", first_name="Exe", last_name="Cutive")
    Profile.objects.create(user=exe, role="executive")
    other = User.objects.create_user("exe2", password="pw-test-123")
    Profile.objects.create(user=other, role="executive")
    project = Project.objects.create(name="Project 1", rera_no="RERA-TEST-1", lat="23.0", lng="72.5")
    return head, exe, other, project


def make_lead(project, phone="9825011111", name="Test Buyer", source="portal", **kw):
    kw.setdefault("created_at", timezone.now())
    kw.setdefault("consent", True)
    return Lead.objects.create(name=name, phone=phone, phone_norm=phone[-10:], source=source,
                               project=project, chat_token="tok" + phone, **kw)


def make_slot(project, exe, hours_ahead=30):
    start = (timezone.now() + timedelta(hours=hours_ahead)).replace(minute=0, second=0, microsecond=0)
    return VisitSlot.objects.create(project=project, executive=exe, start=start)
