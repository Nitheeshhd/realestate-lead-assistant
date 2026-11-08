from django.conf import settings
from django.db import models
from django.db.models import Q


class Profile(models.Model):
    ROLES = [("sales_head", "Sales head"), ("executive", "Sales executive")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLES, default="executive")

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Project(models.Model):
    name = models.CharField(max_length=120)
    rera_no = models.CharField(max_length=80)
    address = models.CharField(max_length=240, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self):
        return self.name

    @property
    def map_url(self):
        if self.lat is None or self.lng is None:
            return ""
        return f"https://www.google.com/maps?q={self.lat},{self.lng}"


class FactSheetEntry(models.Model):
    """The only source the assistant may state facts from."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="facts")
    key = models.CharField(max_length=80)
    value = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("project", "key")]
        ordering = ["project_id", "key"]


class Lead(models.Model):
    SOURCES = [("portal", "Property portal"), ("social", "Social media ad"),
               ("website", "Website"), ("hoarding", "Hoarding call")]
    STATUSES = [("new", "New"), ("chatting", "Chatting"), ("handed_off", "Handed off"),
                ("booked", "Visit booked"), ("visited", "Visited"), ("closed", "Closed")]
    code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    phone_norm = models.CharField(max_length=15, db_index=True)
    source = models.CharField(max_length=20, choices=SOURCES)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="leads")
    wants = models.CharField(max_length=40, blank=True)
    budget = models.CharField(max_length=60, blank=True)
    language = models.CharField(max_length=5, default="en")
    consent = models.BooleanField(default=False)
    opt_out = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUSES, default="new")
    duplicate_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="duplicates")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    chat_token = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField()
    first_response_at = models.DateTimeField(null=True, blank=True)
    human_contact_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.code:
            self.code = f"LD-{58000 + self.pk}"
            super().save(update_fields=["code"])

    @property
    def is_duplicate(self):
        return self.duplicate_of_id is not None


class ChatMessage(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10)  # user | assistant
    content = models.TextField()
    flagged = models.BooleanField(default=False)
    flag_reason = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class VisitSlot(models.Model):
    """One executive, one project, one hour. Capacity is 1 (assumption)."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="slots")
    executive = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    start = models.DateTimeField()

    class Meta:
        unique_together = [("executive", "start")]
        ordering = ["start"]


class Visit(models.Model):
    STATUSES = [("booked", "Booked"), ("visited", "Visited"), ("no_show", "No show"), ("cancelled", "Cancelled")]
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="visits")
    slot = models.ForeignKey(VisitSlot, on_delete=models.PROTECT, related_name="visits")
    status = models.CharField(max_length=12, choices=STATUSES, default="booked")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # The database, not the AI, guarantees no double booking.
            models.UniqueConstraint(fields=["slot"], condition=Q(status="booked"), name="one_booked_visit_per_slot"),
            models.UniqueConstraint(fields=["lead"], condition=Q(status="booked"), name="one_open_visit_per_lead"),
        ]


class Reminder(models.Model):
    KINDS = [("t_minus_1d", "1 day before"), ("t_minus_2h", "2 hours before")]
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name="reminders")
    kind = models.CharField(max_length=12, choices=KINDS)
    send_at = models.DateTimeField()
    status = models.CharField(max_length=10, default="pending")  # pending | sent | skipped
    sent_at = models.DateTimeField(null=True, blank=True)
    body = models.TextField(blank=True)


class Handoff(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="handoffs")
    executive = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    reason = models.CharField(max_length=60)
    summary = models.TextField()
    flagged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class SourceSpend(models.Model):
    """Monthly ad/portal spend per source. Seeded sample data (assumption)."""
    source = models.CharField(max_length=20, choices=Lead.SOURCES)
    month = models.DateField()  # first day of month
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = [("source", "month")]
