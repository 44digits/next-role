from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from django.utils import timezone


class Company(models.Model):
    name = models.CharField(max_length=200, unique=True)
    website = models.URLField(blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CompanyLink(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="links")
    label = models.CharField(max_length=120)
    url = models.URLField()

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return f"{self.company}: {self.label}"


class Contact(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="contacts"
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    title = models.CharField(max_length=160, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    linkedin_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    last_contacted_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class Job(models.Model):
    class Status(models.TextChoices):
        FOUND = "found", "Job found"
        APPLIED = "applied", "Applied"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RECRUITER_SCREEN = "recruiter_screen", "Recruiter screen"
        INTERVIEW = "interview", "Interview"
        OFFER = "offer", "Offer extended"
        DENIED = "denied", "Rejected"

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="jobs")
    title = models.CharField(max_length=200)
    posting_url = models.URLField()
    location = models.CharField(max_length=200, blank=True)
    salary_range = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.FOUND
    )
    found_on = models.DateField(default=timezone.localdate)
    applied_on = models.DateField(null=True, blank=True)
    contacts = models.ManyToManyField(
        Contact, through="JobContact", related_name="jobs", blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "company__name", "title"]

    def __str__(self):
        return f"{self.title} at {self.company}"

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        tracks_status = update_fields is None or "status" in update_fields
        applied_statuses = {
            self.Status.APPLIED,
            self.Status.ACKNOWLEDGED,
            self.Status.RECRUITER_SCREEN,
            self.Status.INTERVIEW,
            self.Status.OFFER,
            self.Status.DENIED,
        }
        if (
            tracks_status
            and self.status in applied_statuses
            and self.applied_on is None
        ):
            self.applied_on = timezone.localdate()
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"applied_on"}

        previous_status = None
        if self.pk and tracks_status:
            previous_status = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )

        with transaction.atomic():
            super().save(*args, **kwargs)
            current_status = self.status if tracks_status else previous_status
            if previous_status != current_status:
                JobStatusHistory.objects.create(
                    job=self,
                    from_status=previous_status or "",
                    to_status=current_status,
                )


class JobStatusHistory(models.Model):
    job = models.ForeignKey(
        Job, on_delete=models.CASCADE, related_name="status_history"
    )
    from_status = models.CharField(
        max_length=32, choices=Job.Status.choices, blank=True
    )
    to_status = models.CharField(max_length=32, choices=Job.Status.choices)
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-changed_at", "-pk"]
        verbose_name_plural = "job status histories"

    def __str__(self):
        return f"{self.job}: {self.get_to_status_display()}"


class JobContact(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job", "contact"], name="unique_job_contact"
            )
        ]

    def clean(self):
        if self.job_id and self.contact_id:
            if self.job.company_id != self.contact.company_id:
                raise ValidationError(
                    {"contact": "A contact must belong to the job's company."}
                )

    def __str__(self):
        return f"{self.contact} on {self.job}"


class JobLink(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="links")
    label = models.CharField(max_length=120)
    url = models.URLField()

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return f"{self.job}: {self.label}"


class Interaction(models.Model):
    class Kind(models.TextChoices):
        EMAIL = "email", "Email"
        LINKEDIN = "linkedin", "LinkedIn message"
        PHONE = "phone", "Phone call"
        INTERVIEW = "interview", "Interview"
        OTHER = "other", "Other"

    class Direction(models.TextChoices):
        OUTBOUND = "outbound", "Outbound"
        INBOUND = "inbound", "Inbound"

    contact = models.ForeignKey(
        Contact, on_delete=models.CASCADE, related_name="interactions"
    )
    job = models.ForeignKey(
        Job,
        on_delete=models.SET_NULL,
        related_name="interactions",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    direction = models.CharField(
        max_length=12, choices=Direction.choices, default=Direction.OUTBOUND
    )
    occurred_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-occurred_at", "-pk"]

    def clean(self):
        if self.job_id and self.contact_id:
            if self.job.company_id != self.contact.company_id:
                raise ValidationError(
                    {"job": "The selected job must belong to the contact's company."}
                )
            if not self.job.contacts.filter(pk=self.contact_id).exists():
                raise ValidationError(
                    {
                        "job": (
                            "Link the contact to the job before logging "
                            "this interaction."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            previous_contact_id = None
            if self.pk:
                previous_contact_id = (
                    type(self)
                    .objects.filter(pk=self.pk)
                    .values_list("contact_id", flat=True)
                    .first()
                )
            super().save(*args, **kwargs)
            self._refresh_contact_dates(previous_contact_id, self.contact_id)

    @staticmethod
    def _refresh_contact_dates(*contact_ids):
        for contact_id in set(filter(None, contact_ids)):
            last_contacted_at = Interaction.objects.filter(
                contact_id=contact_id
            ).aggregate(latest=models.Max("occurred_at"))["latest"]
            Contact.objects.filter(pk=contact_id).update(
                last_contacted_at=last_contacted_at
            )

    def __str__(self):
        return f"{self.get_kind_display()} with {self.contact}"


def validate_pdf_upload(upload):
    if upload.size > 10 * 1024 * 1024:
        raise ValidationError("PDF files must be 10 MB or smaller.")
    if not upload.name.lower().endswith(".pdf"):
        raise ValidationError("Only PDF files are allowed.")
    header = upload.read(5)
    upload.seek(0)
    if header != b"%PDF-":
        raise ValidationError("The uploaded file does not appear to be a PDF.")


def job_document_upload_path(instance, filename):
    return f"job-documents/{instance.job_id}/{uuid4().hex}.pdf"


class JobDocument(models.Model):
    class Kind(models.TextChoices):
        JOB_DESCRIPTION = "job_description", "Job description"
        RESUME = "resume", "Resume"
        APPLICATION = "application", "Job application"
        COVER_LETTER = "cover_letter", "Cover letter"
        OTHER = "other", "Other"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    original_name = models.CharField(max_length=255)
    extracted_text = models.TextField(blank=True)
    file = models.FileField(
        upload_to=job_document_upload_path,
        validators=[FileExtensionValidator(["pdf"]), validate_pdf_upload],
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.get_kind_display()} for {self.job}"


class Task(models.Model):
    title = models.CharField(max_length=200)
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="tasks",
        null=True,
        blank=True,
    )
    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="tasks",
        null=True,
        blank=True,
    )
    due_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["completed_at", "due_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(contact__isnull=False) | models.Q(job__isnull=False)
                ),
                name="task_requires_job_or_contact",
            )
        ]

    def clean(self):
        if not self.contact_id and not self.job_id:
            raise ValidationError("A task must be linked to a contact, a job, or both.")
        if self.contact_id and self.job_id:
            if self.contact.company_id != self.job.company_id:
                raise ValidationError(
                    "A task's contact and job must belong to the same company."
                )
            if not self.job.contacts.filter(pk=self.contact_id).exists():
                raise ValidationError(
                    "Link the contact to the job before creating this task."
                )

    @property
    def is_completed(self):
        return self.completed_at is not None

    def __str__(self):
        return self.title
