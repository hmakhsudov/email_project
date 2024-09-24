from rest_framework import serializers
from .models import ParsingConfig

class ParsingConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParsingConfig
        fields = '__all__'
