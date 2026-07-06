from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

UPDATE_CATEGORY_CHOICES = [
    ("major", "major"),
    ("minor", "minor"),
    ("future", "future"),
]


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Project(TimeStampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="tracked_projects",
        help_text="User who owns and can manage this project",
    )
    project_name = models.CharField(max_length=200)
    developer_names = models.CharField(max_length=255)
    developer_emails = models.TextField()
    notification_type = models.CharField(max_length=100, default="major, minor")
    
    # User preferences
    notify_paused = models.BooleanField(
        default=False,
        help_text="Temporarily pause notifications for this project"
    )
    min_confidence_threshold = models.IntegerField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Only notify about future updates with confidence >= this threshold (0-100)"
    )

    class Meta:
        ordering = ["project_name"]

    def __str__(self):
        return self.project_name


class Library(TimeStampedModel):
    """
    Central source of truth for a library/tool/language.
    Avoids redundant API calls by storing metadata once for multiple projects.
    """
    name = models.CharField(max_length=200, unique=True, db_index=True)
    key = models.CharField(max_length=200, db_index=True, help_text="Normalized key for searching (e.g. 'react', 'python')")
    component_type = models.CharField(max_length=50, default="library", choices=[
        ("library", "Library"), 
        ("language", "Language"),
        ("tool", "Tool")
    ])
    
    # Latest known stable version
    latest_version = models.CharField(max_length=100, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    
    homepage_url = models.URLField(blank=True)
    
    # Version Detection Metadata
    registry_type = models.CharField(max_length=50, blank=True, help_text="Registry type hint (e.g. 'pypi', 'npm')")
    detection_trust_level = models.IntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Trust level of the latest version detection source (0-100)"
    )
    last_api_call_successful = models.BooleanField(default=True)
    api_error_message = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.name} (v{self.latest_version})"


class LibraryRelease(TimeStampedModel):
    """
    History of released versions for a specific Library.
    """
    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="releases")
    version = models.CharField(max_length=100)
    release_date = models.DateField(null=True, blank=True)
    is_security_release = models.BooleanField(default=False)
    summary = models.TextField(blank=True)
    source_url = models.URLField(blank=True)
    detection_source = models.CharField(max_length=100, blank=True, help_text="Source of detection (e.g. 'api:trust_100', 'serper_groq')")
    
    class Meta:
        unique_together = ['library', 'version']
        ordering = ['-release_date', '-created_at']

    def __str__(self):
        return f"{self.library.name} v{self.version}"


class StackComponent(TimeStampedModel):
    project = models.ForeignKey(Project, related_name="components", on_delete=models.CASCADE)
    # Optional link to central Library model (populated via migration/sync)
    library_ref = models.ForeignKey(Library, null=True, blank=True, on_delete=models.SET_NULL, related_name="linked_components")
    
    category = models.CharField(max_length=100)
    key = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    version = models.CharField(max_length=100)
    scope = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.project.project_name} :: {self.name} ({self.version})"


class UpdateCache(TimeStampedModel):
    """Stores detected updates for libraries/languages per project."""
    
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='update_caches',
        help_text="Project this update cache belongs to"
    )
    library = models.CharField(max_length=200, db_index=True)
    version = models.CharField(max_length=100)
    release_date = models.CharField(max_length=50, blank=True)
    category = models.CharField(max_length=10, choices=UPDATE_CATEGORY_CHOICES)
    summary = models.TextField(blank=True)
    source = models.URLField(blank=True)
    detection_method = models.CharField(
        max_length=50,
        blank=True,
        choices=[
            ('registry_api', 'Registry API'),
            ('serper_groq', 'Web Search (Serper+Groq)'),
            ('github_release', 'GitHub Release'),
            ('official_website', 'Official Website'),
            ('unknown', 'Unknown'),
        ],
        default='unknown',
        help_text="Method used to detect this version"
    )
    
    class Meta:
        unique_together = [['project', 'library']]
        ordering = ['-updated_at']
        verbose_name = 'Update Cache'
        verbose_name_plural = 'Update Caches'

    def __str__(self):
        return f"{self.project.project_name} :: {self.library} -> {self.version} ({self.category})"


class UpdateEvent(TimeStampedModel):
    """Append-only project update history event."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="update_events",
    )
    update_cache = models.ForeignKey(
        UpdateCache,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events",
    )
    library = models.CharField(max_length=200, db_index=True)
    from_version = models.CharField(max_length=100, blank=True)
    version = models.CharField(max_length=100)
    release_date = models.CharField(max_length=50, blank=True)
    category = models.CharField(max_length=10, choices=UPDATE_CATEGORY_CHOICES)
    summary = models.TextField(blank=True)
    source = models.URLField(blank=True)
    detection_method = models.CharField(
        max_length=50,
        blank=True,
        choices=[
            ('registry_api', 'Registry API'),
            ('serper_groq', 'Web Search (Serper+Groq)'),
            ('github_release', 'GitHub Release'),
            ('official_website', 'Official Website'),
            ('unknown', 'Unknown'),
        ],
        default='unknown',
        help_text="Method used to detect this version"
    )
    notification_success = models.BooleanField(null=True, blank=True)
    notification_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [["project", "library", "version", "category"]]
        ordering = ["-updated_at"]
        verbose_name = "Update Event"
        verbose_name_plural = "Update Events"

    def __str__(self):
        return f"{self.project.project_name} :: {self.library} {self.from_version} -> {self.version}"


class SecurityVulnerability(TimeStampedModel):
    """OSV-backed vulnerability finding for a project dependency."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("resolved", "Resolved"),
        ("ignored", "Ignored"),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="security_vulnerabilities",
    )
    component = models.ForeignKey(
        StackComponent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="security_vulnerabilities",
    )
    library = models.CharField(max_length=200, db_index=True)
    version = models.CharField(max_length=100)
    ecosystem = models.CharField(max_length=50, db_index=True)
    osv_id = models.CharField(max_length=100, db_index=True)
    aliases = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True)
    details = models.TextField(blank=True)
    severity = models.CharField(max_length=50, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    fixed_versions = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [["project", "library", "version", "ecosystem", "osv_id"]]
        ordering = ["status", "-severity", "-updated_at"]
        verbose_name = "Security Vulnerability"
        verbose_name_plural = "Security Vulnerabilities"

    def __str__(self):
        return f"{self.project.project_name} :: {self.library} {self.version} -> {self.osv_id}"



class FutureUpdateCache(TimeStampedModel):
    """Stores detected future/planned updates separately from released versions."""
    
    library = models.CharField(max_length=200, db_index=True)
    version = models.CharField(max_length=100)
    expected_date = models.DateField(null=True, blank=True, help_text="Expected release date if known")
    confidence = models.IntegerField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Confidence score 0-100% based on source reliability"
    )
    features = models.TextField(blank=True, help_text="Summary of planned features/changes")
    source = models.URLField(blank=True, help_text="URL to announcement/roadmap")
    
    # Status tracking
    STATUS_CHOICES = [
        ('detected', 'Detected'),
        ('confirmed', 'Confirmed'),
        ('released', 'Released'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='detected')
    
    # Link to the actual release when it happens
    promoted_to_release = models.ForeignKey(
        'UpdateCache',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='future_predictions',
        help_text="Links to UpdateCache entry when this future update is released"
    )
    
    # Notification tracking
    notification_sent = models.BooleanField(default=False)
    notification_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Confidence change tracking
    previous_confidence = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Previous confidence level before last update"
    )
    last_change_reason = models.TextField(
        blank=True,
        help_text="Reason for last confidence/info change (e.g., 'Featured on official site')"
    )
    
    # Pre-release Classification
    prerelease_type = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ('alpha', 'Alpha'),
            ('beta', 'Beta'), 
            ('rc', 'Release Candidate'),
            ('dev', 'Development'),
            ('milestone', 'Milestone Only'),
            ('roadmap', 'Roadmap Only'),
        ],
        help_text="Type of pre-release (alpha, beta, rc, etc.)"
    )
    
    detection_method = models.CharField(
        max_length=50,
        blank=True,
        choices=[
            ('registry_prerelease', 'Registry Pre-Release'),
            ('github_release', 'GitHub Pre-Release'),
            ('github_milestone', 'GitHub Milestone'),
            ('github_roadmap', 'GitHub Roadmap File'), 
            ('official_website', 'Official Website/RSS'),
            ('serper_groq', 'Web Search (Fallback)'),
        ],
        help_text="Method used to detect this future version"
    )
    
    is_published_prerelease = models.BooleanField(
        default=False,
        help_text="True if this version is actually installable (e.g. on npm/pypi)"
    )
    
    confirmation_count = models.IntegerField(
        default=1,
        help_text="Number of independent sources confirming this version"
    )
    
    milestone_completion_percent = models.IntegerField(
        null=True,
        blank=True,
        help_text="GitHub milestone completion % if applicable"
    )
    
    class Meta:
        ordering = ['-confidence', '-updated_at']
        unique_together = [['library', 'version']]
        verbose_name = 'Future Update'
        verbose_name_plural = 'Future Updates'
    
    def __str__(self):
        return f"{self.library} {self.version} (future, {self.confidence}% confidence)"


class NotificationRecord(TimeStampedModel):
    """Records notification delivery attempts and results."""

    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notification_records",
        help_text="Project targeted by this notification",
    )
    update_cache = models.ForeignKey(
        UpdateCache,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notification_records",
        help_text="Associated UpdateCache entry when applicable",
    )
    library = models.CharField(max_length=200, db_index=True, blank=True)
    version = models.CharField(max_length=100, blank=True)

    success = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)
    status_text = models.TextField(blank=True)
    http_status = models.IntegerField(null=True, blank=True)
    response_text = models.TextField(blank=True)
    error_text = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification Record"
        verbose_name_plural = "Notification Records"

    def __str__(self):
        proj = self.project.project_name if self.project else "<no project>"
        return f"{proj} :: {self.library} {self.version} -> {'OK' if self.success else 'FAIL'}"


class ProjectFutureNotification(TimeStampedModel):
    """Tracks future-update notification delivery per project."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="future_notifications",
    )
    future_update = models.ForeignKey(
        FutureUpdateCache,
        on_delete=models.CASCADE,
        related_name="project_notifications",
    )
    success = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)
    status_text = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [["project", "future_update"]]
        ordering = ["-updated_at"]
        verbose_name = "Project Future Notification"
        verbose_name_plural = "Project Future Notifications"

    def __str__(self):
        return (
            f"{self.project.project_name} :: "
            f"{self.future_update.library} {self.future_update.version} -> "
            f"{'OK' if self.success else 'PENDING'}"
        )


class FutureUpdateHistory(TimeStampedModel):
    """Records confidence changes and detection updates for FutureUpdateCache."""

    future_update = models.ForeignKey(
        FutureUpdateCache,
        on_delete=models.CASCADE,
        related_name="history_records",
        help_text="Associated FutureUpdateCache entry"
    )
    library = models.CharField(max_length=200, db_index=True)
    version = models.CharField(max_length=100)

    # Confidence tracking
    old_confidence = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    new_confidence = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    # Metadata about the change
    change_reason = models.CharField(
        max_length=100,
        blank=True,
        choices=[
            ('initial_detection', 'Initial Detection'),
            ('source_confirmed', 'Source Confirmed'),
            ('milestone_updated', 'Milestone Updated'),
            ('manual_adjustment', 'Manual Adjustment'),
            ('source_removed', 'Source Removed'),
            ('other', 'Other'),
        ],
        default='other'
    )
    change_notes = models.TextField(blank=True, help_text="Additional context about this change")
    detection_method = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Future Update History"
        verbose_name_plural = "Future Update Histories"

    def __str__(self):
        return f"{self.library} {self.version} @ {self.created_at.strftime('%Y-%m-%d %H:%M')}: {self.old_confidence}% → {self.new_confidence}%"
