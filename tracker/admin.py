from django.contrib import admin
from .models import (
    UpdateCache,
    Project,
    StackComponent,
    FutureUpdateCache,
    NotificationRecord,
    FutureUpdateHistory,
    ProjectFutureNotification,
)

class StackComponentInline(admin.TabularInline):
    model = StackComponent
    extra = 0
    fields = ("category", "name", "version", "scope")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("project_name", "owner", "developer_names", "notification_type", "notify_paused", "min_confidence_threshold", "updated_at")
    search_fields = ("project_name", "developer_names", "developer_emails", "owner__username", "owner__email")
    list_filter = ("notify_paused", "notification_type", "owner")
    fieldsets = (
        ("Project Information", {
            "fields": ("owner", "project_name", "developer_names", "developer_emails", "notification_type")
        }),
        ("Notification Preferences", {
            "fields": ("notify_paused", "min_confidence_threshold"),
            "description": "Control notifications for this project"
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    readonly_fields = ("created_at", "updated_at")
    inlines = [StackComponentInline]


@admin.register(UpdateCache)
class UpdateCacheAdmin(admin.ModelAdmin):
    list_display = ("library","version","category","detection_method","release_date","updated_at")
    search_fields = ("library","version")
    list_filter = ("category", "detection_method")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Core Information", {
            "fields": ("library", "version", "category", "detection_method")
        }),
        ("Release Details", {
            "fields": ("release_date", "summary", "source")
        }),
        ("Project Link", {
            "fields": ("project",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(NotificationRecord)
class NotificationRecordAdmin(admin.ModelAdmin):
    list_display = ("library", "version", "success", "attempts", "http_status", "sent_at", "created_at")
    search_fields = ("library", "version", "project__project_name")
    list_filter = ("success", "http_status")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Notification", {
            "fields": ("project", "library", "version")
        }),
        ("Result", {
            "fields": ("success", "attempts", "sent_at")
        }),
        ("Details", {
            "fields": ("status_text", "http_status", "error_text", "response_text"),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(FutureUpdateHistory)
class FutureUpdateHistoryAdmin(admin.ModelAdmin):
    list_display = ("library", "version", "old_confidence", "new_confidence", "change_reason", "created_at")
    search_fields = ("library", "version")
    list_filter = ("change_reason", "created_at")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Update", {
            "fields": ("future_update", "library", "version")
        }),
        ("Confidence Change", {
            "fields": ("old_confidence", "new_confidence", "change_reason", "detection_method")
        }),
        ("Notes", {
            "fields": ("change_notes",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


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


@admin.register(ProjectFutureNotification)
class ProjectFutureNotificationAdmin(admin.ModelAdmin):
    list_display = ("project", "future_update", "success", "attempts", "sent_at", "updated_at")
    search_fields = (
        "project__project_name",
        "future_update__library",
        "future_update__version",
    )
    list_filter = ("success", "sent_at")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Notification", {
            "fields": ("project", "future_update")
        }),
        ("Result", {
            "fields": ("success", "attempts", "status_text", "sent_at")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
