from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Interaction


@receiver(post_delete, sender=Interaction)
def refresh_contact_last_contacted_after_delete(sender, instance, **kwargs):
    Interaction._refresh_contact_dates(instance.contact_id)
