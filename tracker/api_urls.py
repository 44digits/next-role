from django.urls import path

from .api_views import JobImportAPIView

urlpatterns = [
    path("job-imports/", JobImportAPIView.as_view(), name="job_import"),
]
