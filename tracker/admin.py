from django.contrib import admin
from .models import UpdateCache

@admin.register(UpdateCache)
class UpdateCacheAdmin(admin.ModelAdmin):
    list_display = ("library","version","category","release_date","updated_at")
    search_fields = ("library","version")
    list_filter = ("category",)
    # readonly_fields = ("updated_at",)

    # def save_model(self, request, obj, form, change):
    #     obj.updated_at = None
    #     super().save_model(request, obj, form, change)

    # def save_related(self, request, form, formsets, change):
    #     super().save_related(request, form, formsets, change)
    #     UpdateCache.objects.all().update(updated_at=None)

    # def save_formset(self, request, form, formsets, change):
    #     super().save_formset(request, form, formsets, change)
    #     UpdateCache.objects.all().update(updated_at=None)

    # def save_model(self, request, obj, form, change):
    #     super().save_model(request, obj, form, change)
    #     UpdateCache.objects.all().update(updated_at=None)

