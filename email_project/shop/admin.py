from django.contrib import admin
from .models import ParsingConfig, Order

@admin.register(ParsingConfig)
class ParsingConfigAdmin(admin.ModelAdmin):
    list_display = ('email', 'schedule')
    fields = ('email', 'column_mappings', 'schedule')
    

admin.site.register(Order)