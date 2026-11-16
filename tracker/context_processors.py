from django.utils import timezone

from .forms import QuickInteractionForm
from .models import Job


def quick_interaction(request):
    if not request.user.is_authenticated:
        return {}
    form = QuickInteractionForm(
        initial={"occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M")}
    )
    form.fields["job"].queryset = (
        Job.objects.filter(contacts__isnull=False)
        .distinct()
        .prefetch_related("contacts")
    )
    return {"quick_interaction_form": form}
