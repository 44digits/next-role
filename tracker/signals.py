from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver

from .models import DeletedJobPosting, Interaction, Job, JobLink


@receiver(pre_delete, sender=Job)
def preserve_deleted_job_posting_urls(sender, instance, using, **kwargs):
    posting_urls = JobLink.objects.using(using).filter(
        job_id=instance.pk,
        label="Job posting",
    )
    for posting_url in posting_urls.values_list("url", flat=True):
        DeletedJobPosting.objects.using(using).update_or_create(
            url=posting_url,
            defaults={"original_job_id": instance.pk},
        )


@receiver(post_delete, sender=Interaction)
def refresh_contact_last_contacted_after_delete(sender, instance, **kwargs):
    Interaction._refresh_contact_dates(instance.contact_id)
