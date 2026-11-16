from django.contrib import admin

from .models import (
    Company,
    CompanyLink,
    Contact,
    Interaction,
    Job,
    JobContact,
    JobDocument,
    JobLink,
    JobStatusHistory,
)


class ContactInline(admin.TabularInline):
    model = JobContact
    extra = 0


class JobStatusHistoryInline(admin.TabularInline):
    model = JobStatusHistory
    extra = 0
    readonly_fields = ["from_status", "to_status", "changed_at"]
    can_delete = False


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "website"]
    search_fields = ["name"]


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "status", "applied_on", "updated_at"]
    list_filter = ["status", "company"]
    search_fields = ["title", "company__name"]
    inlines = [ContactInline, JobStatusHistoryInline]


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = [
        "first_name",
        "last_name",
        "company",
        "email",
        "phone",
        "last_contacted_at",
    ]
    list_filter = ["company"]
    search_fields = ["first_name", "last_name", "company__name", "email"]


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ["contact", "job", "kind", "direction", "occurred_at"]
    list_filter = ["kind", "direction"]
    search_fields = ["contact__first_name", "contact__last_name", "job__title", "notes"]


@admin.register(JobDocument)
class JobDocumentAdmin(admin.ModelAdmin):
    list_display = ["original_name", "job", "kind", "uploaded_at"]
    list_filter = ["kind"]
    search_fields = [
        "original_name",
        "job__title",
        "job__company__name",
        "extracted_text",
    ]


admin.site.register([CompanyLink, JobLink, JobStatusHistory])
