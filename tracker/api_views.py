from django.db import transaction
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_permissions import CanImportJobPostings
from .api_serializers import JobImportInputSerializer
from .models import Company, CompanyLink, Job, JobLink


class JobImportAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, CanImportJobPostings]
    parser_classes = [JSONParser]

    def post(self, request):
        serializer = JobImportInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company_data = serializer.validated_data["company"]
        job_data = serializer.validated_data["job"]
        job_links = job_data["links"]
        posting_url = next(
            link["url"] for link in job_links if link["label"] == "Job posting"
        )

        with transaction.atomic():
            existing_job = (
                Job.objects.select_related("company")
                .filter(links__url=posting_url)
                .first()
            )
            if existing_job:
                return Response(
                    self._job_response(existing_job, created=False),
                    status=status.HTTP_200_OK,
                )

            company, _ = Company.objects.get_or_create(name=company_data["name"])
            for link in company_data["links"]:
                CompanyLink.objects.get_or_create(
                    company=company,
                    label=link["label"],
                    url=link["url"],
                )

            job = Job.objects.create(
                company=company,
                title=job_data["title"],
                notes=job_data["notes"],
            )
            JobLink.objects.bulk_create(
                [
                    JobLink(
                        job=job,
                        label=link["label"],
                        url=link["url"],
                    )
                    for link in job_links
                ]
            )

        return Response(
            self._job_response(job, created=True),
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _job_response(job, *, created):
        return {
            "id": job.pk,
            "company": job.company.name,
            "title": job.title,
            "status": job.status,
            "created": created,
        }
