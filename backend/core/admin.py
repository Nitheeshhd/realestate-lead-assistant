from django.contrib import admin

from core import models

for m in (models.Profile, models.Project, models.FactSheetEntry, models.Lead, models.VisitSlot,
          models.Visit, models.Reminder, models.Handoff, models.SourceSpend):
    admin.site.register(m)
