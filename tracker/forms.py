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


class ContactFilterForm(forms.Form):
    company = forms.ModelChoiceField(queryset=Company.objects.all(), required=False)
    role = forms.CharField(required=False)
    inactivity = forms.ChoiceField(
        required=False,
        choices=[
            ("", "Any last-contact date"),
            ("30", "Not contacted in 30+ days"),
            ("60", "Not contacted in 60+ days"),
            ("180", "Not contacted in 180+ days"),
            ("never", "Never contacted"),
        ],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"


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
            "salary_range",
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
        if self.is_bound and self.data.get("company"):
            self.fields["contacts"].queryset = self.fields["contacts"].queryset.filter(
                company_id=self.data.get("company")
            )
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
    contact = forms.ModelChoiceField(queryset=Contact.objects.none())
    occurred_at = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
        ),
    )

    class Meta:
        model = Interaction
        fields = ["contact", "job", "kind", "direction", "occurred_at", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contact"].queryset = Contact.objects.select_related("company")
        contact_id = (
            self.data.get("contact") if self.is_bound else self.initial.get("contact")
        )
        self.fields["job"].queryset = (
            Job.objects.filter(contacts__pk=contact_id).distinct()
            if contact_id
            else Job.objects.none()
        )
        self.fields["job"].required = False

    def clean(self):
        cleaned_data = super().clean()
        contact = cleaned_data.get("contact")
        job = cleaned_data.get("job")
        if contact and job and not job.contacts.filter(pk=contact.pk).exists():
            self.add_error("job", "Choose a job linked to this contact.")
        return cleaned_data


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        clean_one = super().clean
        if isinstance(data, (list, tuple)):
            return [clean_one(item, initial) for item in data]
        if data:
            return [clean_one(data, initial)]
        if self.required:
            return [clean_one(None, initial)]
        return []


class JobDocumentUploadForm(forms.Form):
    kind = forms.ChoiceField(choices=JobDocument.Kind.choices)
    files = MultipleFileField(
        label="PDF files",
        widget=MultipleFileInput(
            attrs={"accept": ".pdf,application/pdf", "multiple": True}
        ),
    )

    def clean_files(self):
        import pdfplumber
        from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect
        from pdfminer.pdfparser import PDFSyntaxError

        files = self.cleaned_data["files"]
        extracted = []
        for upload in files:
            for validator in JobDocument._meta.get_field("file").validators:
                validator(upload)
            upload.seek(0)
            try:
                with pdfplumber.open(upload) as pdf:
                    text = "\n".join(
                        page.extract_text() or "" for page in pdf.pages
                    ).strip()
            except (
                PDFEncryptionError,
                PDFPasswordIncorrect,
                PDFSyntaxError,
                ValueError,
                OSError,
            ) as exc:
                raise forms.ValidationError(
                    f"{upload.name} could not be read as a PDF."
                ) from exc
            finally:
                upload.seek(0)
            extracted.append((upload, text))
        return extracted

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"


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


class DocumentSearchForm(forms.Form):
    query = forms.CharField(required=False, label="Search document text")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["query"].widget.attrs["class"] = "input"
