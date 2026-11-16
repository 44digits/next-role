from django.urls import path

from . import views

urlpatterns = [
    path("", views.board, name="board"),
    path("jobs/new/", views.job_create, name="job_create"),
    path("jobs/<int:pk>/", views.job_detail, name="job_detail"),
    path("jobs/<int:pk>/edit/", views.job_update, name="job_update"),
    path("jobs/<int:pk>/status/", views.job_change_status, name="job_change_status"),
    path("jobs/<int:pk>/links/new/", views.job_link_create, name="job_link_create"),
    path(
        "jobs/<int:pk>/links/<int:link_pk>/delete/",
        views.job_link_delete,
        name="job_link_delete",
    ),
    path(
        "jobs/<int:pk>/documents/new/",
        views.job_document_upload,
        name="job_document_upload",
    ),
    path(
        "jobs/<int:pk>/documents/<int:document_pk>/",
        views.job_document_download,
        name="job_document_download",
    ),
    path(
        "jobs/<int:pk>/documents/<int:document_pk>/preview/",
        views.job_document_preview,
        name="job_document_preview",
    ),
    path(
        "jobs/<int:pk>/documents/<int:document_pk>/delete/",
        views.job_document_delete,
        name="job_document_delete",
    ),
    path("companies/", views.company_list, name="company_list"),
    path("companies/new/", views.company_create, name="company_create"),
    path("companies/<int:pk>/", views.company_detail, name="company_detail"),
    path("companies/<int:pk>/edit/", views.company_update, name="company_update"),
    path(
        "companies/<int:pk>/links/new/",
        views.company_link_create,
        name="company_link_create",
    ),
    path(
        "companies/<int:pk>/links/<int:link_pk>/delete/",
        views.company_link_delete,
        name="company_link_delete",
    ),
    path("contacts/", views.contact_list, name="contact_list"),
    path("contacts/new/", views.contact_create, name="contact_create"),
    path("contacts/<int:pk>/", views.contact_detail, name="contact_detail"),
    path("contacts/<int:pk>/edit/", views.contact_update, name="contact_update"),
    path(
        "contacts/<int:contact_pk>/interactions/new/",
        views.interaction_create,
        name="interaction_create",
    ),
    path(
        "interactions/quick/",
        views.quick_interaction,
        name="quick_interaction",
    ),
    path("documents/search/", views.document_search, name="document_search"),
    path("reports/", views.reports, name="reports"),
]
