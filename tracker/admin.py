from django.contrib import admin

from .models import (
    Company,
    CompanyLink,
    Contact,
    DeletedJobPosting,
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


class CompanyLinkInline(admin.TabularInline):
    model = CompanyLink
    extra = 1
    min_num = 1
    validate_min = True


class JobLinkInline(admin.TabularInline):
    model = JobLink
    extra = 1
    min_num = 1
    validate_min = True


class JobStatusHistoryInline(admin.TabularInline):
    model = JobStatusHistory
    extra = 0
    readonly_fields = ["from_status", "to_status", "changed_at"]
    can_delete = False


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "link_count"]
    search_fields = ["name"]
    inlines = [CompanyLinkInline]

    @admin.display(description="Links")
    def link_count(self, obj):
        return obj.links.count()


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "status", "updated_at"]
    list_filter = ["company"]
    search_fields = ["title", "company__name"]
    inlines = [JobLinkInline, ContactInline, JobStatusHistoryInline]


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
    list_display = ["job", "contact", "kind", "occurred_at"]
    list_filter = ["kind"]
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


@admin.register(DeletedJobPosting)
class DeletedJobPostingAdmin(admin.ModelAdmin):
    list_display = ["url", "original_job_id", "deleted_at"]
    search_fields = ["url"]
    readonly_fields = ["url", "original_job_id", "deleted_at"]

    def has_add_permission(self, request):
        return False
