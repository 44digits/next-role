import tempfile
from datetime import timedelta

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
    Task,
)


class JobStatusHistoryTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Example Inc.")
        self.job = Job.objects.create(
            company=self.company,
            title="Engineer",
            posting_url="https://example.com/jobs/1",
        )

    def test_status_list_has_acknowledged_recruiter_screen_and_one_interview(self):
        self.assertEqual(
            Job.Status.values,
            [
                "found",
                "applied",
                "acknowledged",
                "recruiter_screen",
                "interview",
                "offer",
                "denied",
            ],
        )

    def test_initial_status_and_each_change_are_recorded(self):
        self.job.status = Job.Status.APPLIED
        self.job.save(update_fields=["status"])
        self.assertEqual(self.job.applied_on, timezone.localdate())
        self.job.status = Job.Status.ACKNOWLEDGED
        self.job.save(update_fields=["status"])
        self.job.status = Job.Status.RECRUITER_SCREEN
        self.job.save(update_fields=["status"])
        self.job.status = Job.Status.INTERVIEW
        self.job.save(update_fields=["status"])

        history = list(self.job.status_history.order_by("pk"))
        self.assertEqual(
            [(entry.from_status, entry.to_status) for entry in history],
            [
                ("", Job.Status.FOUND),
                (Job.Status.FOUND, Job.Status.APPLIED),
                (Job.Status.APPLIED, Job.Status.ACKNOWLEDGED),
                (Job.Status.ACKNOWLEDGED, Job.Status.RECRUITER_SCREEN),
                (Job.Status.RECRUITER_SCREEN, Job.Status.INTERVIEW),
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

    def test_interaction_keeps_last_contacted_date_in_sync(self):
        contact = Contact.objects.create(
            company=self.company, first_name="Casey", last_name="Recruiter"
        )
        earlier = Interaction.objects.create(
            contact=contact,
            kind=Interaction.Kind.EMAIL,
            occurred_at=timezone.now() - timedelta(days=4),
        )
        later = Interaction.objects.create(
            contact=contact,
            kind=Interaction.Kind.LINKEDIN,
            occurred_at=timezone.now() - timedelta(days=1),
        )
        self.assertEqual(
            contact.__class__.objects.get(pk=contact.pk).last_contacted_at,
            later.occurred_at,
        )

        Interaction.objects.filter(pk=later.pk).delete()
        contact.refresh_from_db()
        self.assertEqual(contact.last_contacted_at, earlier.occurred_at)

    def test_task_requires_job_or_contact(self):
        task = Task(title="Follow up", due_at=timezone.now())

        with self.assertRaises(ValidationError):
            task.full_clean()


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
                "direction": Interaction.Direction.OUTBOUND,
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
        contact.refresh_from_db()
        self.assertIsNotNone(contact.last_contacted_at)

    def test_global_interaction_can_schedule_follow_up_task(self):
        contact = Contact.objects.create(
            company=self.company, first_name="Taylor", last_name="Recruiter"
        )
        JobContact.objects.create(job=self.job, contact=contact)

        response = self.client.post(
            reverse("quick_interaction"),
            {
                "contact": contact.pk,
                "job": self.job.pk,
                "kind": Interaction.Kind.EMAIL,
                "direction": Interaction.Direction.OUTBOUND,
                "occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "notes": "Follow-up sent.",
                "create_follow_up": "on",
                "task_title": "Check in next week",
                "task_due_at": (timezone.localtime() + timedelta(days=7)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "task_notes": "Ask about the application.",
            },
        )

        self.assertRedirects(response, reverse("board"))
        interaction = Interaction.objects.get()
        task = Task.objects.get()
        self.assertEqual(interaction.contact, contact)
        self.assertEqual(interaction.job, self.job)
        self.assertEqual(task.contact, contact)
        self.assertEqual(task.job, self.job)
        self.assertEqual(task.title, "Check in next week")

    def test_task_completion_updates_task_center(self):
        task = Task.objects.create(
            title="Prepare questions",
            contact=Contact.objects.create(
                company=self.company, first_name="Morgan", last_name="Recruiter"
            ),
            due_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.post(
            reverse("task_toggle", args=[task.pk]),
            {"next": reverse("task_list")},
        )

        self.assertRedirects(response, reverse("task_list"))
        task.refresh_from_db()
        self.assertIsNotNone(task.completed_at)

    def test_contact_directory_filters_by_role_and_inactivity(self):
        stale = Contact.objects.create(
            company=self.company,
            first_name="Stale",
            last_name="Recruiter",
            title="Recruiter",
        )
        recent = Contact.objects.create(
            company=self.company,
            first_name="Recent",
            last_name="Recruiter",
            title="Recruiter",
        )
        Contact.objects.create(
            company=self.company,
            first_name="Other",
            last_name="Role",
            title="Engineer",
        )
        Interaction.objects.create(
            contact=stale,
            kind=Interaction.Kind.EMAIL,
            occurred_at=timezone.now() - timedelta(days=45),
        )
        Interaction.objects.create(
            contact=recent,
            kind=Interaction.Kind.EMAIL,
            occurred_at=timezone.now() - timedelta(days=5),
        )

        response = self.client.get(
            reverse("contact_list"), {"role": "recruit", "inactivity": "30"}
        )

        self.assertEqual(list(response.context["contacts"]), [stale])

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

        Interaction.objects.create(
            contact=stale,
            kind=Interaction.Kind.EMAIL,
            occurred_at=timezone.now() - timedelta(days=200),
        )
        Interaction.objects.create(
            contact=recent,
            kind=Interaction.Kind.PHONE,
            occurred_at=timezone.now() - timedelta(days=10),
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
            }["Rejected"],
            1,
        )
        stale_ids = {
            contact.pk for contact in response.context["stale_buckets"][-1]["contacts"]
        }
        self.assertEqual(stale_ids, {stale.pk, never.pk})

    def test_reports_calculate_funnel_and_weekly_outreach(self):
        today = timezone.localdate()
        applied = Job.objects.create(
            company=self.company,
            title="Applied",
            posting_url="https://example.com/jobs/applied",
            status=Job.Status.APPLIED,
            applied_on=today,
        )
        interviewed = Job.objects.create(
            company=self.company,
            title="Interviewed",
            posting_url="https://example.com/jobs/interviewed",
            status=Job.Status.APPLIED,
            applied_on=today,
        )
        interviewed.status = Job.Status.ACKNOWLEDGED
        interviewed.save(update_fields=["status"])
        interviewed.status = Job.Status.RECRUITER_SCREEN
        interviewed.save(update_fields=["status"])
        interviewed.status = Job.Status.INTERVIEW
        interviewed.save(update_fields=["status"])
        offered = Job.objects.create(
            company=self.company,
            title="Offer",
            posting_url="https://example.com/jobs/offer",
            status=Job.Status.APPLIED,
            applied_on=today,
        )
        offered.status = Job.Status.ACKNOWLEDGED
        offered.save(update_fields=["status"])
        offered.status = Job.Status.RECRUITER_SCREEN
        offered.save(update_fields=["status"])
        offered.status = Job.Status.INTERVIEW
        offered.save(update_fields=["status"])
        offered.status = Job.Status.OFFER
        offered.save(update_fields=["status"])
        contact = Contact.objects.create(
            company=self.company, first_name="Jordan", last_name="Recruiter"
        )
        JobContact.objects.create(job=applied, contact=contact)
        Interaction.objects.create(
            contact=contact,
            job=applied,
            kind=Interaction.Kind.EMAIL,
            direction=Interaction.Direction.OUTBOUND,
        )
        Interaction.objects.create(
            contact=contact,
            job=applied,
            kind=Interaction.Kind.PHONE,
            direction=Interaction.Direction.OUTBOUND,
        )
        Interaction.objects.create(
            contact=contact,
            job=applied,
            kind=Interaction.Kind.EMAIL,
            direction=Interaction.Direction.INBOUND,
        )

        response = self.client.get(
            reverse("reports"),
            {
                "start_date": today.isoformat(),
                "end_date": today.isoformat(),
            },
        )

        self.assertEqual(
            [(item["count"], item["percent"]) for item in response.context["funnel"]],
            [(3, 100), (2, 67), (2, 100), (2, 100), (1, 50)],
        )
        self.assertEqual(len(response.context["weekly_outreach"]), 1)
        self.assertEqual(response.context["weekly_outreach"][0]["total"], 2)

    def test_document_upload_and_download(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                upload = SimpleUploadedFile(
                    "resume.pdf",
                    _make_pdf("sample document"),
                    content_type="application/pdf",
                )
                response = self.client.post(
                    reverse("job_document_upload", args=[self.job.pk]),
                    {"kind": JobDocument.Kind.RESUME, "files": [upload]},
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
                    _make_pdf("sample document"),
                )
                self.assertIn("sample document", document.extracted_text)

    def test_multiple_documents_are_searchable_and_previewable(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse("job_document_upload", args=[self.job.pk]),
                    {
                        "kind": JobDocument.Kind.JOB_DESCRIPTION,
                        "files": [
                            SimpleUploadedFile(
                                "description.pdf",
                                _make_pdf("Distributed systems"),
                                content_type="application/pdf",
                            ),
                            SimpleUploadedFile(
                                "requirements.pdf",
                                _make_pdf("PostgreSQL and Python"),
                                content_type="application/pdf",
                            ),
                        ],
                    },
                )
                self.assertRedirects(
                    response, reverse("job_detail", args=[self.job.pk])
                )
                self.assertEqual(JobDocument.objects.count(), 2)

                response = self.client.get(
                    reverse("document_search"), {"query": "PostgreSQL"}
                )
                self.assertContains(response, "requirements.pdf")
                document = JobDocument.objects.get(original_name="description.pdf")
                preview = self.client.get(
                    reverse(
                        "job_document_preview",
                        args=[self.job.pk, document.pk],
                    )
                )
                self.assertEqual(preview["Content-Type"], "application/pdf")
                self.assertIn("inline", preview["Content-Disposition"])

    def test_invalid_pdf_upload_is_rejected(self):
        upload = SimpleUploadedFile(
            "not-a-pdf.pdf", b"not a pdf", content_type="application/pdf"
        )
        response = self.client.post(
            reverse("job_document_upload", args=[self.job.pk]),
            {"kind": JobDocument.Kind.OTHER, "files": [upload]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(JobDocument.objects.exists())

    def test_tracker_pages_require_login(self):
        self.client.logout()

        response = self.client.get(reverse("board"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('board')}")


def _make_pdf(text):
    content = f"BT /F1 12 Tf 30 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(content)).encode()
        + b" >>\nstream\n"
        + content
        + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(pdf)
