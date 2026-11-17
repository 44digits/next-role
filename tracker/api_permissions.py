from rest_framework.permissions import BasePermission


class CanImportJobPostings(BasePermission):
    message = "You do not have permission to import job postings."

    def has_permission(self, request, view):
        return request.user.has_perm("tracker.import_job_postings")
