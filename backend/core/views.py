import csv
import io
import re
import secrets
from datetime import date, datetime, time, timedelta

from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.models import (ChatMessage, FactSheetEntry, Handoff, Lead, Project, Reminder,
                         Visit, VisitSlot)
from core.permissions import IsSalesHead, IsStaff, role_of
from core.services import agent, dashboard, leads as lead_svc, reminders
from core.services.booking import cancel_visit


def name_of(u):
    return (u.get_full_name() or u.username) if u else None


def lead_row(l):
    return {"id": l.id, "code": l.code, "name": l.name, "phone": l.phone, "source": l.source,
            "source_label": l.get_source_display(), "project": l.project.name, "project_id": l.project_id,
            "wants": l.wants, "budget": l.budget, "language": l.language, "status": l.status,
            "status_label": l.get_status_display(), "is_duplicate": l.is_duplicate,
            "duplicate_of": l.duplicate_of.code if l.duplicate_of else None, "opt_out": l.opt_out,
            "assigned_to": name_of(l.assigned_to), "created_at": l.created_at,
            "response_seconds": round((l.first_response_at - l.created_at).total_seconds()) if l.first_response_at else None}


def visible_leads(user):
    qs = Lead.objects.select_related("project", "assigned_to", "duplicate_of")
    return qs if role_of(user) == "sales_head" else qs.filter(assigned_to=user)


# ---------- auth ----------
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        user = authenticate(username=request.data.get("username", ""), password=request.data.get("password", ""))
        if not user or not role_of(user):
            return Response({"detail": "Wrong username or password."}, status=400)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "role": role_of(user), "name": name_of(user)})


class MeView(APIView):
    def get(self, request):
        return Response({"name": name_of(request.user), "role": role_of(request.user)})


# ---------- public buyer chat ----------
class ProjectsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response([{"id": p.id, "name": p.name, "rera_no": p.rera_no, "address": p.address}
                         for p in Project.objects.all()])


class ChatStartSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=30)
    project_id = serializers.IntegerField()
    language = serializers.ChoiceField(choices=["en", "hi", "gu"], default="en")
    source = serializers.ChoiceField(choices=[s for s, _ in Lead.SOURCES], default="website")
    consent = serializers.BooleanField()


class ChatStartView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "chat_start"

    def post(self, request):
        s = ChatStartSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if not d["consent"]:
            return Response({"detail": "Please accept the consent box to start the chat."}, status=400)
        project = Project.objects.filter(pk=d["project_id"]).first()
        if not project:
            return Response({"detail": "Unknown project."}, status=400)
        try:
            phone_norm = lead_svc.normalize_phone(d["phone"])
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        primary = lead_svc.find_primary(phone_norm)
        if primary:  # same buyer coming back: continue the same chat, do not create a second lead
            lead = primary
            lead.consent = True
            lead.opt_out = False
            lead.project = project
            lead.chat_token = lead.chat_token or secrets.token_urlsafe(24)
            lead.save()
        else:
            lead, _ = lead_svc.create_lead(name=d["name"], phone=d["phone"], source=d["source"], project=project,
                                           language=d["language"], consent=True)
        return Response({"lead_id": lead.id, "token": lead.chat_token, "language": lead.language,
                         "rera_no": project.rera_no, "project": project.name,
                         "opt_out": lead.opt_out,
                         "history": [{"role": m.role, "content": m.content} for m in lead.messages.all()]})


def get_chat_lead(lead_id, token):
    lead = Lead.objects.select_related("project").filter(pk=lead_id).first()
    if not lead or not token or not secrets.compare_digest(lead.chat_token, str(token)):
        return None
    return lead


class ChatMessageView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "chat"

    def post(self, request, lead_id):
        lead = get_chat_lead(lead_id, request.data.get("token"))
        if not lead:
            return Response({"detail": "Chat session not found."}, status=404)
        text = str(request.data.get("message", "")).strip()
        if not text or len(text) > 600:
            return Response({"detail": "Write a message of up to 600 characters."}, status=400)
        if lead.opt_out:
            return Response({"detail": "This chat has opted out. Start a new chat with consent to resume."}, status=403)
        return Response(agent.respond(lead, text))


class ChatOptOutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, lead_id):
        lead = get_chat_lead(lead_id, request.data.get("token"))
        if not lead:
            return Response({"detail": "Chat session not found."}, status=404)
        lead.opt_out = True
        lead.save(update_fields=["opt_out"])
        return Response({"ok": True})


# ---------- staff: leads ----------
class LeadListView(APIView):
    permission_classes = [IsStaff]

    def get(self, request):
        qs = visible_leads(request.user)
        p = request.query_params
        if p.get("source"):
            qs = qs.filter(source=p["source"])
        if p.get("project"):
            qs = qs.filter(project_id=p["project"])
        if p.get("duplicates") == "1":
            qs = qs.filter(duplicate_of__isnull=False)
        if p.get("q"):
            qs = qs.filter(Q(name__icontains=p["q"]) | Q(code__icontains=p["q"]) | Q(phone_norm__icontains=p["q"]))
        return Response([lead_row(l) for l in qs[:300]])

    def post(self, request):
        """Add one lead by hand (or from a portal export row). Duplicates are flagged, not dropped."""
        d = request.data
        project = Project.objects.filter(pk=d.get("project_id")).first()
        if not project or d.get("source") not in dict(Lead.SOURCES) or not str(d.get("name", "")).strip():
            return Response({"detail": "Name, source and project are required."}, status=400)
        try:
            lead, primary = lead_svc.create_lead(name=d["name"], phone=d.get("phone", ""), source=d["source"],
                                                 project=project, wants=d.get("wants", ""), consent=bool(d.get("consent")))
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response({**lead_row(lead), "duplicate": primary is not None}, status=201)


class LeadImportView(APIView):
    permission_classes = [IsSalesHead]

    def post(self, request):
        f = request.FILES.get("file")
        if not f or f.size > 1_000_000:
            return Response({"detail": "Upload a CSV file under 1 MB."}, status=400)
        reader = csv.DictReader(io.StringIO(f.read().decode("utf-8-sig", errors="replace")))
        projects = {p.name.lower(): p for p in Project.objects.all()}
        created = dupes = 0
        errors = []
        for i, row in enumerate(reader, start=2):
            try:
                project = projects.get((row.get("project") or "").strip().lower())
                if not project or (row.get("source") or "") not in dict(Lead.SOURCES):
                    raise ValueError("unknown project or source")
                _, primary = lead_svc.create_lead(name=row.get("name") or "Unknown", phone=row.get("phone", ""),
                                                  source=row["source"], project=project, wants=row.get("wants", ""))
                created += 1
                dupes += 1 if primary else 0
            except (ValueError, KeyError) as e:
                errors.append(f"Row {i}: {e}")
        return Response({"created": created, "duplicates": dupes, "errors": errors[:20]})


class LeadDetailView(APIView):
    permission_classes = [IsStaff]

    def get(self, request, pk):
        lead = visible_leads(request.user).filter(pk=pk).first()
        if not lead:
            return Response({"detail": "Lead not found."}, status=404)
        visits = lead.visits.select_related("slot__executive", "slot__project").order_by("-created_at")
        return Response({
            **lead_row(lead),
            "messages": [{"role": m.role, "content": m.content, "flagged": m.flagged, "flag_reason": m.flag_reason,
                          "at": m.created_at} for m in lead.messages.all()],
            "visits": [{"id": v.id, "status": v.status, "start": v.slot.start, "executive": name_of(v.slot.executive),
                        "reminders": [{"kind": r.get_kind_display(), "send_at": r.send_at, "status": r.status}
                                      for r in v.reminders.all()]} for v in visits],
            "handoffs": [{"id": h.id, "reason": h.reason, "summary": h.summary, "created_at": h.created_at}
                         for h in lead.handoffs.all()],
        })


class VisitStatusView(APIView):
    permission_classes = [IsStaff]

    def post(self, request, pk):
        visit = Visit.objects.filter(pk=pk, lead__in=visible_leads(request.user)).first()
        new = request.data.get("status")
        if not visit or new not in ("visited", "no_show", "cancelled"):
            return Response({"detail": "Visit not found or status not allowed."}, status=400)
        if new == "cancelled":
            cancel_visit(visit)
        else:
            if visit.slot.start > timezone.now():
                return Response({"detail": "You can only mark a visit after its slot has started."}, status=400)
            visit.status = new
            visit.save(update_fields=["status"])
            if new == "visited":
                visit.lead.status = "visited"
                visit.lead.save(update_fields=["status"])
        return Response({"ok": True})


# ---------- staff: handoffs and review ----------
def handoff_row(h):
    return {"id": h.id, "lead_id": h.lead_id, "lead_code": h.lead.code, "lead_name": h.lead.name,
            "phone": h.lead.phone, "source_label": h.lead.get_source_display(), "project": h.lead.project.name,
            "reason": h.reason, "summary": h.summary, "flagged": h.flagged, "executive": name_of(h.executive),
            "acknowledged_at": h.acknowledged_at, "reviewed_at": h.reviewed_at, "created_at": h.created_at}


class HandoffListView(APIView):
    permission_classes = [IsStaff]

    def get(self, request):
        qs = Handoff.objects.select_related("lead__project", "executive")
        if role_of(request.user) != "sales_head":
            qs = qs.filter(executive=request.user)
        if request.query_params.get("review") == "1":
            if role_of(request.user) != "sales_head":
                return Response({"detail": "Only the sales head can open the review queue."}, status=403)
            qs = qs.filter(flagged=True, reviewed_at__isnull=True)
        return Response([handoff_row(h) for h in qs[:200]])


class HandoffActionView(APIView):
    permission_classes = [IsStaff]

    def post(self, request, pk, action):
        h = Handoff.objects.select_related("lead__project", "executive").filter(pk=pk).first()
        if not h or (role_of(request.user) != "sales_head" and h.executive_id != request.user.id):
            return Response({"detail": "Handoff not found."}, status=404)
        now = timezone.now()
        if action == "ack":
            h.acknowledged_at = h.acknowledged_at or now
            if not h.lead.human_contact_at:
                h.lead.human_contact_at = now
                h.lead.save(update_fields=["human_contact_at"])
        elif action == "review":
            if role_of(request.user) != "sales_head":
                return Response({"detail": "Only the sales head can review."}, status=403)
            h.reviewed_at = now
        else:
            return Response({"detail": "Unknown action."}, status=400)
        h.save()
        return Response(handoff_row(h))


# ---------- dashboard ----------
class DashboardView(APIView):
    permission_classes = [IsSalesHead]

    def get(self, request):
        today = timezone.localdate()
        try:
            d_to = date.fromisoformat(request.query_params.get("to", today.isoformat()))
            d_from = date.fromisoformat(request.query_params.get("from", (d_to - timedelta(days=29)).isoformat()))
        except ValueError:
            return Response({"detail": "Dates must look like 2026-11-04."}, status=400)
        if d_from > d_to or (d_to - d_from).days > 366:
            return Response({"detail": "Choose a range of up to one year."}, status=400)
        project = request.query_params.get("project")
        return Response(dashboard.build(d_from, d_to, int(project) if project and project.isdigit() else None))


# ---------- admin: fact sheet, slots, reminders ----------
class FactSerializer(serializers.ModelSerializer):
    class Meta:
        model = FactSheetEntry
        fields = ["id", "project", "key", "value", "updated_at"]
        read_only_fields = ["updated_at"]
        validators = []

    def validate_key(self, v):
        v = re.sub(r"\s+", "_", v.strip().lower())
        if not re.fullmatch(r"[a-z0-9_]{2,60}", v):
            raise serializers.ValidationError("Use letters, numbers and underscores, e.g. possession_date.")
        return v


class FactListView(APIView):
    permission_classes = [IsSalesHead]

    def get(self, request):
        qs = FactSheetEntry.objects.all()
        if request.query_params.get("project"):
            qs = qs.filter(project_id=request.query_params["project"])
        return Response(FactSerializer(qs, many=True).data)

    def post(self, request):
        s = FactSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj, _ = FactSheetEntry.objects.update_or_create(
            project=s.validated_data["project"], key=s.validated_data["key"],
            defaults={"value": s.validated_data["value"]})
        return Response(FactSerializer(obj).data, status=201)


class FactDetailView(APIView):
    permission_classes = [IsSalesHead]

    def delete(self, request, pk):
        n, _ = FactSheetEntry.objects.filter(pk=pk).delete()
        return Response(status=204 if n else 404)


class ExecutivesView(APIView):
    permission_classes = [IsSalesHead]

    def get(self, request):
        users = get_user_model().objects.filter(profile__role="executive")
        return Response([{"id": u.id, "name": name_of(u)} for u in users])


class SlotListView(APIView):
    permission_classes = [IsSalesHead]

    def get(self, request):
        qs = VisitSlot.objects.filter(start__gte=timezone.now()).select_related("executive", "project")
        if request.query_params.get("project"):
            qs = qs.filter(project_id=request.query_params["project"])
        booked = set(Visit.objects.filter(status="booked").values_list("slot_id", flat=True))
        return Response([{"id": s.id, "project": s.project.name, "project_id": s.project_id,
                          "executive": name_of(s.executive), "executive_id": s.executive_id,
                          "start": s.start, "booked": s.id in booked}
                         for s in qs[:400]])

    def post(self, request):
        """Open slots for one executive on one day: {project, executive, date, hours:[10,11,...]}."""
        d = request.data
        project = Project.objects.filter(pk=d.get("project")).first()
        exe = get_user_model().objects.filter(pk=d.get("executive"), profile__role="executive").first()
        try:
            day = date.fromisoformat(d.get("date", ""))
            hours = sorted({int(h) for h in d.get("hours", [])})
        except (ValueError, TypeError):
            return Response({"detail": "Pick a date and at least one hour."}, status=400)
        if not project or not exe or not hours or any(h < 7 or h > 20 for h in hours):
            return Response({"detail": "Choose a project, an executive and hours between 7 and 20."}, status=400)
        tz = timezone.get_current_timezone()
        created = 0
        for h in hours:
            start = timezone.make_aware(datetime.combine(day, time(h)), tz)
            if start <= timezone.now():
                continue
            _, new = VisitSlot.objects.get_or_create(project=project, executive=exe, start=start)
            created += int(new)
        return Response({"created": created}, status=201)


class SlotUpdateSerializer(serializers.Serializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    executive = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(profile__role="executive"))
    date = serializers.DateField()
    hour = serializers.IntegerField(min_value=7, max_value=20)


class SlotDetailView(APIView):
    permission_classes = [IsSalesHead]

    def patch(self, request, pk):
        slot = VisitSlot.objects.filter(pk=pk).first()
        if not slot:
            return Response({"detail": "Slot not found."}, status=404)
        if Visit.objects.filter(slot=slot, status="booked").exists():
            return Response({"detail": "This slot has a booked visit and cannot be changed."}, status=409)

        s = SlotUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        start = timezone.make_aware(datetime.combine(d["date"], time(d["hour"])),
                                    timezone.get_current_timezone())
        if start <= timezone.now():
            return Response({"detail": "Choose a future date and time."}, status=400)
        if VisitSlot.objects.filter(executive=d["executive"], start=start).exclude(pk=slot.pk).exists():
            return Response({"detail": "This executive already has a slot at that time."}, status=409)
        slot.project = d["project"]
        slot.executive = d["executive"]
        slot.start = start
        try:
            with transaction.atomic():
                slot.save(update_fields=["project", "executive", "start"])
        except IntegrityError:
            return Response({"detail": "This executive already has a slot at that time."}, status=409)
        return Response({"id": slot.id, "project": slot.project.name, "project_id": slot.project_id,
                         "executive": name_of(slot.executive), "executive_id": slot.executive_id,
                         "start": slot.start, "booked": False})

    def delete(self, request, pk):
        slot = VisitSlot.objects.filter(pk=pk).first()
        if not slot:
            return Response(status=404)
        if Visit.objects.filter(slot=slot, status="booked").exists():
            return Response({"detail": "This slot has a booked visit. Cancel the visit first."}, status=409)
        slot.delete()
        return Response(status=204)


class RunRemindersView(APIView):
    permission_classes = [IsSalesHead]

    def post(self, request):
        return Response(reminders.dispatch_due())


class SentRemindersView(APIView):
    permission_classes = [IsSalesHead]

    def get(self, request):
        qs = Reminder.objects.exclude(status="pending").select_related("visit__lead").order_by("-sent_at")[:50]
        return Response([{"id": r.id, "lead": r.visit.lead.name, "kind": r.get_kind_display(), "status": r.status,
                          "body": r.body, "sent_at": r.sent_at} for r in qs])
