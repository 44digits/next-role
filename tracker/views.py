from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncWeek
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    ApplicationReportForm,
    CompanyForm,
    CompanyLinkForm,
    ContactFilterForm,
    ContactForm,
    DocumentSearchForm,
    JobDocumentUploadForm,
    JobForm,
    JobLinkForm,
    QuickInteractionForm,
    TaskForm,
)
from .models import (
    Company,
    CompanyLink,
    Contact,
    Interaction,
    Job,
    JobDocument,
    JobLink,
    JobStatusHistory,
    Task,
)


@login_required
def board(request):
    jobs = Job.objects.select_related("company").prefetch_related("contacts")
    jobs_by_status = {status: [] for status, _ in Job.Status.choices}
    for job in jobs:
        jobs_by_status[job.status].append(job)

    columns = [
        {"key": status, "label": label, "jobs": jobs_by_status[status]}
        for status, label in Job.Status.choices
    ]
    overdue_tasks, upcoming_tasks = _pending_tasks()
    return render(
        request,
        "tracker/board.html",
        {
            "columns": columns,
            "status_choices": Job.Status.choices,
            "overdue_tasks": overdue_tasks,
            "upcoming_tasks": upcoming_tasks,
        },
    )


@login_required
def job_create(request):
    data = request.POST if request.method == "POST" else None
    form = JobForm(data)
    if request.method == "POST" and form.is_valid():
        job = form.save()
        messages.success(request, "Job added.")
        return redirect("job_detail", pk=job.pk)
    return render(request, "tracker/form_page.html", {"form": form, "title": "Add job"})


@login_required
def job_detail(request, pk):
    job = get_object_or_404(
        Job.objects.select_related("company").prefetch_related(
            "contacts", "links", "documents", "status_history", "interactions", "tasks"
        ),
        pk=pk,
    )
    activity = [
        {
            "timestamp": entry.changed_at,
            "kind": "status",
            "entry": entry,
        }
        for entry in job.status_history.all()
    ]
    activity.extend(
        {
            "timestamp": entry.occurred_at,
            "kind": "interaction",
            "entry": entry,
        }
        for entry in job.interactions.select_related("contact")
    )
    activity.sort(key=lambda item: item["timestamp"], reverse=True)
    return render(
        request,
        "tracker/job_detail.html",
        {
            "job": job,
            "activity": activity,
            "open_tasks": job.tasks.filter(completed_at__isnull=True),
        },
    )


@login_required
def job_update(request, pk):
    job = get_object_or_404(Job, pk=pk)
    data = request.POST if request.method == "POST" else None
    form = JobForm(data, instance=job)
    if request.method == "POST" and form.is_valid():
        job = form.save()
        messages.success(request, "Job updated.")
        return redirect("job_detail", pk=job.pk)
    return render(
        request,
        "tracker/form_page.html",
        {"form": form, "title": f"Edit {job.title}"},
    )


@login_required
@require_POST
def job_change_status(request, pk):
    job = get_object_or_404(Job, pk=pk)
    status = request.POST.get("status", "")
    if status not in Job.Status.values:
        messages.error(request, "Choose a valid job status.")
    else:
        job.status = status
        job.save(update_fields=["status", "updated_at"])
        messages.success(request, "Job status updated.")
    return _safe_redirect(request, request.POST.get("next"), "board")


@login_required
def company_list(request):
    companies = Company.objects.annotate(job_count=Count("jobs")).order_by("name")
    return render(request, "tracker/company_list.html", {"companies": companies})


@login_required
def company_create(request):
    data = request.POST if request.method == "POST" else None
    form = CompanyForm(data)
    if request.method == "POST" and form.is_valid():
        company = form.save()
        messages.success(request, "Company added.")
        return redirect("company_detail", pk=company.pk)
    return render(
        request, "tracker/form_page.html", {"form": form, "title": "Add company"}
    )


@login_required
def company_detail(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return render(request, "tracker/company_detail.html", {"company": company})


@login_required
def company_update(request, pk):
    company = get_object_or_404(Company, pk=pk)
    data = request.POST if request.method == "POST" else None
    form = CompanyForm(data, instance=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Company updated.")
        return redirect("company_detail", pk=company.pk)
    return render(
        request,
        "tracker/form_page.html",
        {"form": form, "title": f"Edit {company.name}"},
    )


@login_required
def company_link_create(request, pk):
    company = get_object_or_404(Company, pk=pk)
    data = request.POST if request.method == "POST" else None
    form = CompanyLinkForm(data)
    if request.method == "POST" and form.is_valid():
        link = form.save(commit=False)
        link.company = company
        link.save()
        messages.success(request, "Company link added.")
        return redirect("company_detail", pk=company.pk)
    return render(
        request,
        "tracker/form_page.html",
        {"form": form, "title": f"Add link for {company.name}"},
    )


@login_required
@require_POST
def company_link_delete(request, pk, link_pk):
    company = get_object_or_404(Company, pk=pk)
    get_object_or_404(CompanyLink, pk=link_pk, company=company).delete()
    messages.success(request, "Company link removed.")
    return redirect("company_detail", pk=company.pk)


@login_required
def contact_list(request):
    form = ContactFilterForm(request.GET)
    contacts = Contact.objects.select_related("company")
    if form.is_valid():
        company = form.cleaned_data.get("company")
        role = form.cleaned_data.get("role")
        inactivity = form.cleaned_data.get("inactivity")
        if company:
            contacts = contacts.filter(company=company)
        if role:
            contacts = contacts.filter(title__icontains=role)
        if inactivity == "never":
            contacts = contacts.filter(last_contacted_at__isnull=True)
        elif inactivity:
            cutoff = timezone.now() - timedelta(days=int(inactivity))
            contacts = contacts.filter(
                Q(last_contacted_at__lte=cutoff) | Q(last_contacted_at__isnull=True)
            )
    return render(
        request, "tracker/contact_list.html", {"contacts": contacts, "form": form}
    )


@login_required
def contact_create(request):
    data = request.POST if request.method == "POST" else None
    form = ContactForm(data)
    if request.method == "POST" and form.is_valid():
        contact = form.save()
        messages.success(request, "Contact added.")
        return redirect("contact_detail", pk=contact.pk)
    return render(
        request, "tracker/form_page.html", {"form": form, "title": "Add contact"}
    )


@login_required
def contact_detail(request, pk):
    contact = get_object_or_404(Contact.objects.select_related("company"), pk=pk)
    interactions = contact.interactions.select_related("job", "job__company")
    return render(
        request,
        "tracker/contact_detail.html",
        {"contact": contact, "interactions": interactions},
    )


@login_required
def contact_update(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    data = request.POST if request.method == "POST" else None
    form = ContactForm(data, instance=contact)
    if request.method == "POST" and form.is_valid():
        contact = form.save()
        messages.success(request, "Contact updated.")
        return redirect("contact_detail", pk=contact.pk)
    return render(
        request,
        "tracker/form_page.html",
        {"form": form, "title": f"Edit {contact.full_name}"},
    )


@login_required
def interaction_create(request, contact_pk):
    contact = get_object_or_404(Contact, pk=contact_pk)
    return _interaction_form_response(
        request,
        initial={"contact": contact.pk},
        fallback_url=reverse("contact_detail", args=[contact.pk]),
    )


@login_required
def quick_interaction(request):
    if request.method != "POST":
        return redirect("board")
    form = QuickInteractionForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            interaction = form.save(commit=False)
            interaction.save()
            if form.cleaned_data["create_follow_up"]:
                Task.objects.create(
                    title=form.cleaned_data["task_title"],
                    contact=interaction.contact,
                    job=interaction.job,
                    due_at=form.cleaned_data["task_due_at"],
                    notes=form.cleaned_data["task_notes"],
                )
        messages.success(request, "Interaction recorded.")
    else:
        messages.error(
            request,
            "; ".join(message for errors in form.errors.values() for message in errors),
        )
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("board")


def _interaction_form_response(request, initial, fallback_url):
    data = request.POST.copy() if request.method == "POST" else None
    if data is not None and initial.get("contact"):
        data["contact"] = str(initial["contact"])
    form = QuickInteractionForm(data, initial=initial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            interaction = form.save(commit=False)
            interaction.save()
            if form.cleaned_data["create_follow_up"]:
                Task.objects.create(
                    title=form.cleaned_data["task_title"],
                    contact=interaction.contact,
                    job=interaction.job,
                    due_at=form.cleaned_data["task_due_at"],
                    notes=form.cleaned_data["task_notes"],
                )
        messages.success(request, "Interaction recorded.")
        return redirect(fallback_url)
    return render(
        request,
        "tracker/form_page.html",
        {"form": form, "title": "Record an interaction"},
    )


@login_required
def job_link_create(request, pk):
    job = get_object_or_404(Job, pk=pk)
    data = request.POST if request.method == "POST" else None
    form = JobLinkForm(data)
    if request.method == "POST" and form.is_valid():
        link = form.save(commit=False)
        link.job = job
        link.save()
        messages.success(request, "Job link added.")
        return redirect("job_detail", pk=job.pk)
    return render(
        request,
        "tracker/form_page.html",
        {"form": form, "title": f"Add link for {job.title}"},
    )


@login_required
@require_POST
def job_link_delete(request, pk, link_pk):
    job = get_object_or_404(Job, pk=pk)
    get_object_or_404(JobLink, pk=link_pk, job=job).delete()
    messages.success(request, "Job link removed.")
    return redirect("job_detail", pk=job.pk)


@login_required
def job_document_upload(request, pk):
    job = get_object_or_404(Job, pk=pk)
    data = request.POST if request.method == "POST" else None
    files = request.FILES.getlist("files") if request.method == "POST" else None
    form = JobDocumentUploadForm(data, {"files": files} if files else None)
    if request.method == "POST" and form.is_valid():
        for upload, extracted_text in form.cleaned_data["files"]:
            JobDocument.objects.create(
                job=job,
                kind=form.cleaned_data["kind"],
                original_name=upload.name[:255],
                extracted_text=extracted_text,
                file=upload,
            )
        messages.success(request, "PDF documents added.")
        return redirect("job_detail", pk=job.pk)
    return render(
        request,
        "tracker/form_page.html",
        {"form": form, "title": f"Add documents for {job.title}"},
    )


@login_required
def job_document_download(request, pk, document_pk):
    document = get_object_or_404(JobDocument, pk=document_pk, job_id=pk)
    document.file.open("rb")
    return FileResponse(
        document.file,
        as_attachment=True,
        filename=document.original_name,
        content_type="application/pdf",
    )


@login_required
def job_document_preview(request, pk, document_pk):
    document = get_object_or_404(JobDocument, pk=document_pk, job_id=pk)
    document.file.open("rb")
    response = FileResponse(
        document.file,
        as_attachment=False,
        filename=document.original_name,
        content_type="application/pdf",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_POST
def job_document_delete(request, pk, document_pk):
    job = get_object_or_404(Job, pk=pk)
    document = get_object_or_404(JobDocument, pk=document_pk, job=job)
    document.file.delete(save=False)
    document.delete()
    messages.success(request, "Document removed.")
    return redirect("job_detail", pk=job.pk)


@login_required
def document_search(request):
    form = DocumentSearchForm(request.GET)
    documents = JobDocument.objects.select_related("job", "job__company").none()
    if form.is_valid() and form.cleaned_data["query"]:
        query = form.cleaned_data["query"].strip()
        documents = (
            JobDocument.objects.select_related("job", "job__company")
            .filter(
                Q(extracted_text__icontains=query)
                | Q(original_name__icontains=query)
                | Q(job__title__icontains=query)
                | Q(job__company__name__icontains=query)
            )
            .distinct()
        )
    return render(
        request,
        "tracker/document_search.html",
        {"form": form, "documents": documents},
    )


@login_required
def task_list(request):
    overdue_tasks, upcoming_tasks = _pending_tasks()
    completed_tasks = Task.objects.filter(completed_at__isnull=False).select_related(
        "contact", "job", "job__company"
    )
    return render(
        request,
        "tracker/task_list.html",
        {
            "overdue_tasks": overdue_tasks,
            "upcoming_tasks": upcoming_tasks,
            "completed_tasks": completed_tasks,
        },
    )


@login_required
def task_create(request):
    data = request.POST if request.method == "POST" else None
    initial = {
        key: value for key in ("contact", "job") if (value := request.GET.get(key))
    }
    form = TaskForm(data, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Task added.")
        return redirect("task_list")
    return render(
        request, "tracker/form_page.html", {"form": form, "title": "Add task"}
    )


@login_required
@require_POST
def task_toggle(request, pk):
    task = get_object_or_404(Task, pk=pk)
    task.completed_at = None if task.completed_at else timezone.now()
    task.save(update_fields=["completed_at"])
    messages.success(
        request, "Task reopened." if task.completed_at is None else "Task completed."
    )
    return _safe_redirect(request, request.POST.get("next"), "task_list")


def _pending_tasks():
    now = timezone.now()
    related = ("contact", "job", "job__company")
    incomplete = Task.objects.filter(completed_at__isnull=True).select_related(*related)
    overdue = incomplete.filter(due_at__lt=now).order_by("due_at")
    upcoming = incomplete.filter(due_at__gte=now).order_by("due_at")
    return overdue, upcoming


def _safe_redirect(request, destination, fallback):
    if destination and url_has_allowed_host_and_scheme(
        destination, allowed_hosts={request.get_host()}
    ):
        return redirect(destination)
    return redirect(fallback)


@login_required
def reports(request):
    form = ApplicationReportForm(request.GET)
    applied_jobs = Job.objects.filter(applied_on__isnull=False)
    interactions = Interaction.objects.filter(direction=Interaction.Direction.OUTBOUND)
    if form.is_valid():
        start_date = form.cleaned_data.get("start_date")
        end_date = form.cleaned_data.get("end_date")
        if start_date:
            applied_jobs = applied_jobs.filter(applied_on__gte=start_date)
            interactions = interactions.filter(occurred_at__date__gte=start_date)
        if end_date:
            applied_jobs = applied_jobs.filter(applied_on__lte=end_date)
            interactions = interactions.filter(occurred_at__date__lte=end_date)
    else:
        applied_jobs = applied_jobs.none()
        interactions = interactions.none()

    status_totals = dict(
        applied_jobs.values("status")
        .annotate(total=Count("pk"))
        .values_list("status", "total")
    )
    status_counts = [
        {"label": label, "count": status_totals.get(status, 0)}
        for status, label in Job.Status.choices
    ]
    funnel = _application_funnel(applied_jobs)
    weekly_rows = list(
        interactions.annotate(week=TruncWeek("occurred_at"))
        .values("week", "kind")
        .annotate(total=Count("pk"))
        .order_by("week", "kind")
    )
    weekly_outreach = _weekly_outreach(weekly_rows)

    contacts = Contact.objects.select_related("company")
    stale_buckets = []
    for days in (30, 60, 180):
        cutoff = timezone.now() - timedelta(days=days)
        stale = contacts.filter(
            Q(last_contacted_at__lte=cutoff) | Q(last_contacted_at__isnull=True)
        ).order_by("company__name", "last_name", "first_name")
        stale_buckets.append(
            {
                "days": days,
                "contacts": stale,
                "count": stale.count(),
            }
        )
    overdue_tasks, upcoming_tasks = _pending_tasks()
    return render(
        request,
        "tracker/reports.html",
        {
            "form": form,
            "status_counts": status_counts,
            "total_applications": sum(item["count"] for item in status_counts),
            "funnel": funnel,
            "weekly_outreach": weekly_outreach,
            "stale_buckets": stale_buckets,
            "overdue_tasks": overdue_tasks,
            "upcoming_tasks": upcoming_tasks,
        },
    )


def _application_funnel(applied_jobs):
    applied_ids = list(applied_jobs.values_list("pk", flat=True))
    if not applied_ids:
        return [
            {"label": label, "count": 0, "percent": 0}
            for label in ("Applied", "Interview", "Offer extended")
        ]

    interview_ids = _jobs_reaching_statuses(applied_ids, {Job.Status.INTERVIEW})
    offer_ids = _jobs_reaching_statuses(applied_ids, {Job.Status.OFFER})
    applied_count = len(applied_ids)
    interview_count = len(interview_ids)
    offer_count = len(offer_ids)
    return [
        {
            "label": "Applied",
            "count": applied_count,
            "percent": 100 if applied_count else 0,
        },
        {
            "label": "Interview",
            "count": interview_count,
            "percent": round(interview_count / applied_count * 100),
        },
        {
            "label": "Offer extended",
            "count": offer_count,
            "percent": round(offer_count / interview_count * 100)
            if interview_count
            else 0,
        },
    ]


def _jobs_reaching_statuses(job_ids, statuses):
    reached_ids = set(
        JobStatusHistory.objects.filter(
            job_id__in=job_ids, to_status__in=statuses
        ).values_list("job_id", flat=True)
    )
    reached_ids.update(
        Job.objects.filter(pk__in=job_ids, status__in=statuses).values_list(
            "pk", flat=True
        )
    )
    return reached_ids


def _weekly_outreach(rows):
    kinds = list(Interaction.Kind.choices)
    weeks = {}
    for row in rows:
        week = row["week"]
        weeks.setdefault(week, {kind: 0 for kind, _ in kinds})
        weeks[week][row["kind"]] = row["total"]
    maximum = max((sum(values.values()) for values in weeks.values()), default=0)
    return [
        {
            "week": week,
            "counts": [
                {
                    "kind": kind,
                    "label": label,
                    "count": values[kind],
                    "percent": round(values[kind] / maximum * 100) if maximum else 0,
                }
                for kind, label in kinds
            ],
            "total": sum(values.values()),
        }
        for week, values in sorted(weeks.items())
    ]
