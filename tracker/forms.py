from django import forms

from .models import (
    Company,
    CompanyLink,
    Contact,
    Interaction,
    Job,
    JobDocument,
    JobLink,
)


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "checkbox")
            elif isinstance(widget, forms.CheckboxSelectMultiple):
                continue
            else:
                widget.attrs.setdefault("class", "input")


class CompanyForm(StyledModelForm):
    class Meta:
        model = Company
        fields = ["name", "website", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class CompanyLinkForm(StyledModelForm):
    class Meta:
        model = CompanyLink
        fields = ["label", "url"]


class ContactForm(StyledModelForm):
    class Meta:
        model = Contact
        fields = [
            "company",
            "first_name",
            "last_name",
            "title",
            "email",
            "phone",
            "linkedin_url",
            "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}


class JobForm(StyledModelForm):
    contacts = forms.ModelMultipleChoiceField(
        queryset=Contact.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Job
        fields = [
            "company",
            "title",
            "posting_url",
            "location",
            "salary",
            "description",
            "notes",
            "status",
            "found_on",
            "applied_on",
            "contacts",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "notes": forms.Textarea(attrs={"rows": 4}),
            "found_on": forms.DateInput(attrs={"type": "date"}),
            "applied_on": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contacts"].queryset = Contact.objects.select_related("company")
        if self.instance.pk:
            self.fields["contacts"].initial = self.instance.contacts.all()

    def clean_contacts(self):
        contacts = self.cleaned_data["contacts"]
        company = self.cleaned_data.get("company")
        if company and any(contact.company_id != company.pk for contact in contacts):
            raise forms.ValidationError(
                "Each selected contact must belong to the job's company."
            )
        return contacts


class JobLinkForm(StyledModelForm):
    class Meta:
        model = JobLink
        fields = ["label", "url"]


class InteractionForm(StyledModelForm):
    occurred_at = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
        ),
    )

    class Meta:
        model = Interaction
        fields = ["job", "kind", "occurred_at", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, company_id: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["job"].queryset = Job.objects.filter(company_id=company_id)
        self.fields["job"].required = False


class JobDocumentForm(StyledModelForm):
    class Meta:
        model = JobDocument
        fields = ["kind", "file"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].widget.attrs["accept"] = ".pdf,application/pdf"


class ApplicationReportForm(forms.Form):
    start_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    end_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError("End date must be on or after start date.")
        return cleaned_data
