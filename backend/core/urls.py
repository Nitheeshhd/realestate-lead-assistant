from django.urls import path

from core import views as v

urlpatterns = [
    path("auth/login", v.LoginView.as_view()),
    path("auth/me", v.MeView.as_view()),
    path("public/projects", v.ProjectsView.as_view()),
    path("chat/start", v.ChatStartView.as_view()),
    path("chat/<int:lead_id>/message", v.ChatMessageView.as_view()),
    path("chat/<int:lead_id>/opt-out", v.ChatOptOutView.as_view()),
    path("leads", v.LeadListView.as_view()),
    path("leads/import", v.LeadImportView.as_view()),
    path("leads/<int:pk>", v.LeadDetailView.as_view()),
    path("visits/<int:pk>/status", v.VisitStatusView.as_view()),
    path("handoffs", v.HandoffListView.as_view()),
    path("handoffs/<int:pk>/<str:action>", v.HandoffActionView.as_view()),
    path("dashboard", v.DashboardView.as_view()),
    path("facts", v.FactListView.as_view()),
    path("facts/<int:pk>", v.FactDetailView.as_view()),
    path("executives", v.ExecutivesView.as_view()),
    path("slots", v.SlotListView.as_view()),
    path("slots/<int:pk>", v.SlotDetailView.as_view()),
    path("reminders/run", v.RunRemindersView.as_view()),
    path("reminders", v.SentRemindersView.as_view()),
]
