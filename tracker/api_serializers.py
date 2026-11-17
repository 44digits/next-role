from rest_framework import serializers


class LinkInputSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=120)
    url = serializers.URLField()


class CompanyInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    links = LinkInputSerializer(many=True, allow_empty=False)


class JobInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    links = LinkInputSerializer(many=True, allow_empty=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_links(self, links):
        posting_link_count = sum(link["label"] == "Job posting" for link in links)
        if posting_link_count != 1:
            raise serializers.ValidationError(
                "Include exactly one link labeled 'Job posting'."
            )
        return links


class JobImportInputSerializer(serializers.Serializer):
    company = CompanyInputSerializer()
    job = JobInputSerializer()
