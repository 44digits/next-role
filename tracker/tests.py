import json
import tempfile
from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token

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


class JobStatusHistoryTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Example Inc.")
        self.job = Job.objects.create(
            company=self.company,
            title="Engineer",
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
        self.job.record_status(Job.Status.APPLIED)
        self.job.record_status(Job.Status.ACKNOWLEDGED)
        self.job.record_status(Job.Status.RECRUITER_SCREEN)
        self.job.record_status(Job.Status.INTERVIEW)

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

    def test_saving_other_job_fields_does_not_change_status_history(self):
        self.job.title = "Updated engineer"
        self.job.save(update_fields=["title"])
        self.assertEqual(self.job.status_history.count(), 1)
        self.assertEqual(Job.objects.get(pk=self.job.pk).status, Job.Status.FOUND)

    def test_creating_job_records_initial_found_status(self):
        job = Job.objects.create(
            company=self.company,
            title="Another engineer",
        )

        self.assertEqual(job.status, Job.Status.FOUND)
        self.assertEqual(job.status_history.count(), 1)

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
            job=self.job,
            kind=Interaction.Kind.EMAIL,
            occurred_at=timezone.now() - timedelta(days=4),
        )
        later = Interaction.objects.create(
            contact=contact,
            job=self.job,
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


class TrackerViewTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Example Inc.")
        self.user = User.objects.create_user(
            username="tracker", password="secure-test-password"
        )
        self.job = Job.objects.create(
            company=self.company,
            title="Engineer",
        )
        JobLink.objects.create(
            job=self.job,
            label="Job posting",
            url="https://example.com/jobs/1",
        )
        self.client.force_login(self.user)

    def create_job(self, title, url):
        job = Job.objects.create(company=self.company, title=title)
        JobLink.objects.create(job=job, label="Job posting", url=url)
        return job

    def create_applied_job(self, title, url, applied_at=None, final_status=None):
        job = self.create_job(title, url)
        job.record_status(Job.Status.APPLIED)
        if applied_at:
            JobStatusHistory.objects.filter(
                job=job, to_status=Job.Status.APPLIED
            ).update(changed_at=applied_at)
        if final_status:
            job.record_status(final_status)
        return job

    def test_board_groups_jobs_and_status_change_adds_history(self):
        response = self.client.get(reverse("board"))
        self.assertContains(response, "Engineer")
        self.assertContains(response, "Job found")
        self.assertContains(response, "data-status-form hidden")
        self.assertNotContains(response, f'id="status-{self.job.pk}"')
        self.assertNotContains(response, ">Update</button>")
        self.assertNotContains(response, "Overdue tasks")
        self.assertNotContains(response, "Schedule a follow-up task")

        response = self.client.post(
            reverse("job_change_status", args=[self.job.pk]),
            {"status": Job.Status.APPLIED},
        )
        self.assertRedirects(response, reverse("board"))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.APPLIED)
        self.assertEqual(self.job.status_history.count(), 2)

    def test_job_detail_can_delete_job_and_attached_data(self):
        contact = Contact.objects.create(
            company=self.company, first_name="Casey", last_name="Recruiter"
        )
        JobContact.objects.create(job=self.job, contact=contact)
        interaction = Interaction.objects.create(
            job=self.job,
            contact=contact,
            kind=Interaction.Kind.EMAIL,
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                upload = SimpleUploadedFile(
                    "resume.pdf",
                    _make_pdf("sample document"),
                    content_type="application/pdf",
                )
                self.client.post(
                    reverse("job_document_upload", args=[self.job.pk]),
                    {"kind": JobDocument.Kind.RESUME, "files": [upload]},
                )
                document = JobDocument.objects.get()
                file_name = document.file.name
                self.assertTrue(document.file.storage.exists(file_name))

                response = self.client.get(reverse("job_detail", args=[self.job.pk]))
                self.assertContains(response, "Delete job")

                response = self.client.get(reverse("job_delete", args=[self.job.pk]))
                self.assertEqual(response.status_code, 405)

                response = self.client.post(reverse("job_delete", args=[self.job.pk]))

                self.assertRedirects(response, reverse("board"))
                self.assertFalse(Job.objects.filter(pk=self.job.pk).exists())
                self.assertFalse(
                    JobStatusHistory.objects.filter(job_id=self.job.pk).exists()
                )
                self.assertFalse(Interaction.objects.filter(pk=interaction.pk).exists())
                self.assertFalse(JobDocument.objects.filter(pk=document.pk).exists())
                self.assertFalse(document.file.storage.exists(file_name))
                self.assertTrue(Contact.objects.filter(pk=contact.pk).exists())

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
                "contacts": [contact.pk],
            },
        )

        created_job = Job.objects.get(title="Product engineer")
        self.assertRedirects(response, reverse("job_detail", args=[created_job.pk]))
        self.assertQuerySetEqual(created_job.contacts.all(), [contact])
        self.assertTrue(
            created_job.links.filter(
                label="Job posting",
                url="https://example.com/jobs/product-engineer",
            ).exists()
        )

    def test_company_form_creates_required_company_link(self):
        response = self.client.post(
            reverse("company_create"),
            {
                "name": "New Company",
                "company_url": "https://example.com/company",
                "description": "",
            },
        )

        company = Company.objects.get(name="New Company")
        self.assertRedirects(response, reverse("company_detail", args=[company.pk]))
        self.assertEqual(company.links.count(), 1)
        self.assertEqual(company.links.get().url, "https://example.com/company")

    def test_company_must_retain_at_least_one_link(self):
        link = CompanyLink.objects.create(
            company=self.company,
            label="Website",
            url="https://example.com/company",
        )

        response = self.client.post(
            reverse("company_link_delete", args=[self.company.pk, link.pk])
        )

        self.assertRedirects(
            response, reverse("company_detail", args=[self.company.pk])
        )
        self.assertTrue(CompanyLink.objects.filter(pk=link.pk).exists())

    def test_contact_interaction_form_records_history(self):
        contact = Contact.objects.create(
            company=self.company, first_name="Casey", last_name="Recruiter"
        )
        JobContact.objects.create(job=self.job, contact=contact)

        response = self.client.post(
            reverse("interaction_create", args=[contact.pk]),
            {
                "job": self.job.pk,
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
        contact.refresh_from_db()
        self.assertIsNotNone(contact.last_contacted_at)

    def test_global_interaction_records_interaction(self):
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
                "occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "notes": "Follow-up sent.",
            },
        )

        self.assertRedirects(response, reverse("board"))
        interaction = Interaction.objects.get()
        self.assertEqual(interaction.contact, contact)
        self.assertEqual(interaction.job, self.job)

    def test_interaction_can_be_logged_without_a_contact(self):
        response = self.client.post(
            reverse("quick_interaction"),
            {
                "contact": "",
                "job": self.job.pk,
                "kind": Interaction.Kind.ACKNOWLEDGEMENT,
                "occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "notes": "Application receipt acknowledged.",
            },
        )

        self.assertRedirects(response, reverse("board"))
        interaction = Interaction.objects.get()
        self.assertIsNone(interaction.contact)
        self.assertEqual(interaction.job, self.job)

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
        JobContact.objects.create(job=self.job, contact=stale)
        JobContact.objects.create(job=self.job, contact=recent)
        Interaction.objects.create(
            contact=stale,
            job=self.job,
            kind=Interaction.Kind.EMAIL,
            occurred_at=timezone.now() - timedelta(days=45),
        )
        Interaction.objects.create(
            contact=recent,
            job=self.job,
            kind=Interaction.Kind.EMAIL,
            occurred_at=timezone.now() - timedelta(days=5),
        )

        response = self.client.get(
            reverse("contact_list"), {"role": "recruit", "inactivity": "30"}
        )

        self.assertEqual(list(response.context["contacts"]), [stale])

    def test_invalid_report_range_does_not_show_unfiltered_totals(self):
        self.create_applied_job("Applied job", "https://example.com/jobs/2")

        response = self.client.get(
            reverse("reports"),
            {"start_date": "2026-03-01", "end_date": "2026-02-01"},
        )

        self.assertEqual(response.context["total_applications"], 0)
        self.assertTrue(response.context["form"].errors)

    def test_reports_filter_by_applied_date_and_find_stale_contacts(self):
        today = timezone.localdate()
        self.create_applied_job(
            "Included",
            "https://example.com/jobs/2",
            final_status=Job.Status.DENIED,
        )
        self.create_applied_job(
            "Outside range",
            "https://example.com/jobs/3",
            applied_at=timezone.now() - timedelta(days=100),
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
            job=self.job,
            kind=Interaction.Kind.EMAIL,
            occurred_at=timezone.now() - timedelta(days=200),
        )
        Interaction.objects.create(
            contact=recent,
            job=self.job,
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

    def test_reports_calculate_funnel_and_weekly_interactions(self):
        today = timezone.localdate()
        applied = self.create_applied_job("Applied", "https://example.com/jobs/applied")
        interviewed = self.create_applied_job(
            "Interviewed", "https://example.com/jobs/interviewed"
        )
        interviewed.record_status(Job.Status.ACKNOWLEDGED)
        interviewed.record_status(Job.Status.RECRUITER_SCREEN)
        interviewed.record_status(Job.Status.INTERVIEW)
        offered = self.create_applied_job("Offer", "https://example.com/jobs/offer")
        offered.record_status(Job.Status.ACKNOWLEDGED)
        offered.record_status(Job.Status.RECRUITER_SCREEN)
        offered.record_status(Job.Status.INTERVIEW)
        offered.record_status(Job.Status.OFFER)
        contact = Contact.objects.create(
            company=self.company, first_name="Jordan", last_name="Recruiter"
        )
        JobContact.objects.create(job=applied, contact=contact)
        Interaction.objects.create(
            contact=contact,
            job=applied,
            kind=Interaction.Kind.EMAIL,
        )
        Interaction.objects.create(
            contact=contact,
            job=applied,
            kind=Interaction.Kind.PHONE,
        )
        Interaction.objects.create(
            contact=contact,
            job=applied,
            kind=Interaction.Kind.EMAIL,
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
        self.assertEqual(len(response.context["weekly_interactions"]), 1)
        self.assertEqual(response.context["weekly_interactions"][0]["total"], 3)

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


class JobImportAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="job-scraper")
        permission = Permission.objects.get(
            content_type__app_label="tracker",
            codename="import_job_postings",
        )
        self.user.user_permissions.add(permission)
        self.token = Token.objects.create(user=self.user)
        self.url = reverse("job_import")

    def payload(self, *, company_name="Acme", posting_url=None):
        return {
            "company": {
                "name": company_name,
                "links": [
                    {"label": "Website", "url": "https://acme.example"},
                ],
            },
            "job": {
                "title": "Backend Engineer",
                "links": [
                    {
                        "label": "Job posting",
                        "url": posting_url or "https://careers.acme.example/jobs/123",
                    },
                ],
                "notes": "",
            },
        }

    def post_import(self, payload, *, token=None):
        headers = {}
        if token is not None:
            headers["HTTP_AUTHORIZATION"] = f"Token {token.key}"
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def test_job_import_requires_token_authentication(self):
        response = self.post_import(self.payload())

        self.assertEqual(response.status_code, 401)

    def test_job_import_requires_import_permission(self):
        user = User.objects.create_user(username="other-service")
        token = Token.objects.create(user=user)

        response = self.post_import(self.payload(), token=token)

        self.assertEqual(response.status_code, 403)

    def test_import_creates_company_job_link_and_found_status(self):
        response = self.post_import(self.payload(), token=self.token)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        job = Job.objects.get(pk=data["id"])
        self.assertTrue(data["created"])
        self.assertEqual(job.company.name, "Acme")
        self.assertEqual(job.links.get().url, "https://careers.acme.example/jobs/123")
        self.assertEqual(job.status, Job.Status.FOUND)
        self.assertEqual(
            job.status_history.get().to_status,
            Job.Status.FOUND,
        )
        self.assertEqual(job.company.links.get().url, "https://acme.example")

    def test_import_reuses_company_with_matching_name(self):
        company = Company.objects.create(name="Acme")
        CompanyLink.objects.create(
            company=company,
            label="Website",
            url="https://acme.example",
        )

        response = self.post_import(self.payload(), token=self.token)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Company.objects.filter(name="Acme").count(), 1)
        self.assertEqual(Job.objects.get().company_id, company.pk)

    def test_exact_posting_url_returns_existing_job_before_company_creation(self):
        company = Company.objects.create(name="Existing Co.")
        job = Job.objects.create(company=company, title="Existing role")
        JobLink.objects.create(
            job=job,
            label="Job posting",
            url="https://careers.acme.example/jobs/123",
        )

        response = self.post_import(
            self.payload(company_name="Unrelated Co."),
            token=self.token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": job.pk,
                "company": "Existing Co.",
                "title": "Existing role",
                "status": Job.Status.FOUND,
                "created": False,
            },
        )
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(Job.objects.count(), 1)

    def test_different_posting_url_is_imported_without_fuzzy_matching(self):
        company = Company.objects.create(name="Acme")
        existing_job = Job.objects.create(
            company=company,
            title="Backend Engineer",
        )
        JobLink.objects.create(
            job=existing_job,
            label="Job posting",
            url="https://careers.acme.example/jobs/old",
        )

        response = self.post_import(
            self.payload(posting_url="https://careers.acme.example/jobs/new"),
            token=self.token,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Job.objects.count(), 2)

    def test_import_requires_exactly_one_job_posting_link(self):
        payload = self.payload()
        payload["job"]["links"] = [
            {"label": "Careers", "url": "https://careers.acme.example"}
        ]

        response = self.post_import(payload, token=self.token)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Company.objects.count(), 0)
        self.assertEqual(Job.objects.count(), 0)


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
