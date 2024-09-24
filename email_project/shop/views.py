from rest_framework import viewsets
from .models import ParsingConfig
from .serializers import ParsingConfigSerializer

class ParsingConfigViewSet(viewsets.ModelViewSet):
    queryset = ParsingConfig.objects.all()
    serializer_class = ParsingConfigSerializer
