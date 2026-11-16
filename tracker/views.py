import calendar
from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    ApplicationReportForm,
    CompanyForm,
    CompanyLinkForm,
    ContactForm,
    InteractionForm,
    JobDocumentForm,
    JobForm,
    JobLinkForm,
)
from .models import (
    Company,
    CompanyLink,
    Contact,
    Job,
    JobDocument,
    JobLink,
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
    return render(
        request,
        "tracker/board.html",
        {"columns": columns, "status_choices": Job.Status.choices},
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
            "contacts", "links", "documents", "status_history", "interactions"
        ),
        pk=pk,
    )
    interactions = job.interactions.select_related("contact")
    return render(
        request,
        "tracker/job_detail.html",
        {"job": job, "interactions": interactions},
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
    return redirect("board")


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
    contacts = Contact.objects.select_related("company").annotate(
        last_contacted=Max("interactions__occurred_at")
    )
    return render(request, "tracker/contact_list.html", {"contacts": contacts})


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
    initial = {"occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M")}
    data = request.POST if request.method == "POST" else None
    form = InteractionForm(data, company_id=contact.company_id, initial=initial)
    if request.method == "POST" and form.is_valid():
        interaction = form.save(commit=False)
        interaction.contact = contact
        interaction.save()
        messages.success(request, "Interaction recorded.")
        return redirect("contact_detail", pk=contact.pk)
    return render(
        request,
        "tracker/form_page.html",
        {"form": form, "title": f"Record interaction with {contact.full_name}"},
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
    files = request.FILES if request.method == "POST" else None
    form = JobDocumentForm(data, files)
    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        document.job = job
        document.original_name = form.cleaned_data["file"].name[:255]
        document.save()
        messages.success(request, "PDF added.")
        return redirect("job_detail", pk=job.pk)
    return render(
        request,
        "tracker/form_page.html",
        {"form": form, "title": f"Add document for {job.title}"},
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
@require_POST
def job_document_delete(request, pk, document_pk):
    job = get_object_or_404(Job, pk=pk)
    document = get_object_or_404(JobDocument, pk=document_pk, job=job)
    document.file.delete(save=False)
    document.delete()
    messages.success(request, "Document removed.")
    return redirect("job_detail", pk=job.pk)


def _months_before(value, count):
    month_index = value.month - count - 1
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


@login_required
def reports(request):
    form = ApplicationReportForm(request.GET)
    applied_jobs = Job.objects.filter(applied_on__isnull=False)
    if form.is_valid():
        start_date = form.cleaned_data.get("start_date")
        end_date = form.cleaned_data.get("end_date")
        if start_date:
            applied_jobs = applied_jobs.filter(applied_on__gte=start_date)
        if end_date:
            applied_jobs = applied_jobs.filter(applied_on__lte=end_date)
    else:
        applied_jobs = applied_jobs.none()
    counts = dict(
        applied_jobs.values("status")
        .annotate(total=Count("pk"))
        .values_list("status", "total")
    )
    status_counts = [
        {"label": label, "count": counts.get(status, 0)}
        for status, label in Job.Status.choices
    ]

    cutoff_date = _months_before(timezone.localdate(), 6)
    cutoff = timezone.make_aware(datetime.combine(cutoff_date, time.min))
    stale_contacts = (
        Contact.objects.select_related("company")
        .annotate(last_contacted=Max("interactions__occurred_at"))
        .filter(Q(last_contacted__lt=cutoff) | Q(last_contacted__isnull=True))
        .order_by("company__name", "last_name", "first_name")
    )
    return render(
        request,
        "tracker/reports.html",
        {
            "form": form,
            "status_counts": status_counts,
            "total_applications": sum(item["count"] for item in status_counts),
            "stale_contacts": stale_contacts,
            "cutoff_date": cutoff_date,
        },
    )
