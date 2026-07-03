"""Read-only administration API for RAG evaluation history."""

from rest_framework import generics, serializers

from apps.chat.models import RAGEvaluationRun
from apps.spaces.admin_views import CanViewAdminOperations


class RAGEvaluationRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = RAGEvaluationRun
        fields = [
            "id",
            "requested_by",
            "status",
            "dataset_version",
            "config_fingerprint",
            "metrics",
            "report",
            "created_at",
            "completed_at",
        ]


class RAGEvaluationRunListView(generics.ListAPIView):
    permission_classes = [CanViewAdminOperations]
    serializer_class = RAGEvaluationRunSerializer
    queryset = RAGEvaluationRun.objects.select_related("requested_by").all()
