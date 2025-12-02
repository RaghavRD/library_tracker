from django.contrib import admin
from .models import UpdateCache, Project, StackComponent, FutureUpdateCache

class StackComponentInline(admin.TabularInline):
    model = StackComponent
    extra = 0
    fields = ("category", "name", "version", "scope")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("project_name", "developer_names", "notification_type", "updated_at")
    search_fields = ("project_name", "developer_names", "developer_emails")
    inlines = [StackComponentInline]


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


@admin.register(FutureUpdateCache)
class FutureUpdateCacheAdmin(admin.ModelAdmin):
    list_display = ("library", "version", "confidence", "status", "expected_date", "notification_sent", "updated_at")
    search_fields = ("library", "version", "features")
    list_filter = ("status", "notification_sent", "confidence")
    readonly_fields = ("created_at", "updated_at", "notification_sent_at")
    fieldsets = (
        ("Update Information", {
            "fields": ("library", "version", "confidence", "status")
        }),
        ("Details", {
            "fields": ("expected_date", "features", "source")
        }),
        ("Tracking", {
            "fields": ("promoted_to_release", "notification_sent", "notification_sent_at")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
