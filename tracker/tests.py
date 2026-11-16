import calendar
import tempfile
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Company,
    Contact,
    Interaction,
    Job,
    JobContact,
    JobDocument,
)


class JobStatusHistoryTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Example Inc.")
        self.job = Job.objects.create(
            company=self.company,
            title="Engineer",
            posting_url="https://example.com/jobs/1",
        )

    def test_initial_status_and_each_change_are_recorded(self):
        self.job.status = Job.Status.APPLIED
        self.job.save(update_fields=["status"])
        self.assertEqual(self.job.applied_on, timezone.localdate())
        self.job.status = Job.Status.HR_INTERVIEW
        self.job.save(update_fields=["status"])

        history = list(self.job.status_history.order_by("pk"))
        self.assertEqual(
            [(entry.from_status, entry.to_status) for entry in history],
            [
                ("", Job.Status.FOUND),
                (Job.Status.FOUND, Job.Status.APPLIED),
                (Job.Status.APPLIED, Job.Status.HR_INTERVIEW),
            ],
        )

    def test_status_change_is_not_logged_when_status_is_not_saved(self):
        self.job.status = Job.Status.DENIED
        self.job.save(update_fields=["title"])

        self.assertEqual(self.job.status_history.count(), 1)
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, Job.Status.FOUND)

    def test_creating_applied_job_sets_applied_date(self):
        job = Job.objects.create(
            company=self.company,
            title="Another engineer",
            posting_url="https://example.com/jobs/2",
            status=Job.Status.APPLIED,
        )

        self.assertEqual(job.applied_on, timezone.localdate())

    def test_job_contact_must_belong_to_same_company(self):
        other_company = Company.objects.create(name="Other Inc.")
        contact = Contact.objects.create(
            company=other_company, first_name="Pat", last_name="Person"
        )
        association = JobContact(job=self.job, contact=contact)

        with self.assertRaisesMessage(
            ValidationError, "must belong to the job's company"
        ):
            association.full_clean()


class TrackerViewTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Example Inc.")
        self.user = User.objects.create_user(
            username="tracker", password="secure-test-password"
        )
        self.job = Job.objects.create(
            company=self.company,
            title="Engineer",
            posting_url="https://example.com/jobs/1",
        )
        self.client.force_login(self.user)

    def test_board_groups_jobs_and_status_change_adds_history(self):
        response = self.client.get(reverse("board"))
        self.assertContains(response, "Engineer")
        self.assertContains(response, "Job found")

        response = self.client.post(
            reverse("job_change_status", args=[self.job.pk]),
            {"status": Job.Status.APPLIED},
        )
        self.assertRedirects(response, reverse("board"))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.APPLIED)
        self.assertEqual(self.job.status_history.count(), 2)

    def test_job_form_associates_company_contact(self):
        contact = Contact.objects.create(
            company=self.company, first_name="Casey", last_name="Recruiter"
        )

        response = self.client.post(
            reverse("job_create"),
            {
                "company": self.company.pk,
                "title": "Product engineer",
                "posting_url": "https://example.com/jobs/product-engineer",
                "status": Job.Status.FOUND,
                "found_on": timezone.localdate().isoformat(),
                "contacts": [contact.pk],
            },
        )

        created_job = Job.objects.get(title="Product engineer")
        self.assertRedirects(response, reverse("job_detail", args=[created_job.pk]))
        self.assertQuerySetEqual(created_job.contacts.all(), [contact])

    def test_contact_interaction_form_records_history(self):
        contact = Contact.objects.create(
            company=self.company, first_name="Casey", last_name="Recruiter"
        )

        response = self.client.post(
            reverse("interaction_create", args=[contact.pk]),
            {
                "kind": Interaction.Kind.EMAIL,
                "occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "notes": "Sent a follow-up email.",
            },
        )

        self.assertRedirects(response, reverse("contact_detail", args=[contact.pk]))
        self.assertEqual(contact.interactions.count(), 1)
        self.assertContains(
            self.client.get(reverse("contact_detail", args=[contact.pk])),
            "Sent a follow-up email.",
        )

    def test_invalid_report_range_does_not_show_unfiltered_totals(self):
        Job.objects.create(
            company=self.company,
            title="Applied job",
            posting_url="https://example.com/jobs/2",
            status=Job.Status.APPLIED,
            applied_on=timezone.localdate(),
        )

        response = self.client.get(
            reverse("reports"),
            {"start_date": "2026-03-01", "end_date": "2026-02-01"},
        )

        self.assertEqual(response.context["total_applications"], 0)
        self.assertTrue(response.context["form"].errors)

    def test_reports_filter_by_applied_date_and_find_stale_contacts(self):
        today = timezone.localdate()
        Job.objects.create(
            company=self.company,
            title="Included",
            posting_url="https://example.com/jobs/2",
            status=Job.Status.DENIED,
            applied_on=today,
        )
        Job.objects.create(
            company=self.company,
            title="Outside range",
            posting_url="https://example.com/jobs/3",
            status=Job.Status.APPLIED,
            applied_on=today - timedelta(days=100),
        )
        stale = Contact.objects.create(
            company=self.company, first_name="Stale", last_name="Contact"
        )
        never = Contact.objects.create(
            company=self.company, first_name="Never", last_name="Contact"
        )
        recent = Contact.objects.create(
            company=self.company, first_name="Recent", last_name="Contact"
        )

        cutoff_date = _six_months_before(today)
        cutoff = timezone.make_aware(datetime.combine(cutoff_date, time.min))
        Interaction.objects.create(
            contact=stale,
            kind=Interaction.Kind.EMAIL,
            occurred_at=cutoff - timedelta(seconds=1),
        )
        Interaction.objects.create(
            contact=recent,
            kind=Interaction.Kind.PHONE,
            occurred_at=cutoff + timedelta(days=1),
        )

        response = self.client.get(
            reverse("reports"),
            {
                "start_date": today.isoformat(),
                "end_date": today.isoformat(),
            },
        )

        self.assertEqual(response.context["total_applications"], 1)
        self.assertEqual(
            {
                item["label"]: item["count"]
                for item in response.context["status_counts"]
            }["Denied"],
            1,
        )
        stale_ids = {contact.pk for contact in response.context["stale_contacts"]}
        self.assertEqual(stale_ids, {stale.pk, never.pk})

    def test_document_upload_and_download(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                upload = SimpleUploadedFile(
                    "resume.pdf",
                    b"%PDF-1.4\nsample document",
                    content_type="application/pdf",
                )
                response = self.client.post(
                    reverse("job_document_upload", args=[self.job.pk]),
                    {"kind": JobDocument.Kind.RESUME, "file": upload},
                )
                document = JobDocument.objects.get()
                self.assertRedirects(
                    response, reverse("job_detail", args=[self.job.pk])
                )

                response = self.client.get(
                    reverse(
                        "job_document_download",
                        args=[self.job.pk, document.pk],
                    )
                )

                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertEqual(
                    b"".join(response.streaming_content),
                    b"%PDF-1.4\nsample document",
                )

    def test_invalid_pdf_upload_is_rejected(self):
        upload = SimpleUploadedFile(
            "not-a-pdf.pdf", b"not a pdf", content_type="application/pdf"
        )
        response = self.client.post(
            reverse("job_document_upload", args=[self.job.pk]),
            {"kind": JobDocument.Kind.OTHER, "file": upload},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(JobDocument.objects.exists())

    def test_tracker_pages_require_login(self):
        self.client.logout()

        response = self.client.get(reverse("board"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('board')}")


def _six_months_before(value):
    month_index = value.month - 6 - 1
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
