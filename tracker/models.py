from django.db import models
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
    project_name = models.CharField(max_length=200)
    developer_names = models.CharField(max_length=255)
    developer_emails = models.TextField()
    notification_type = models.CharField(max_length=100, default="major, minor")

    class Meta:
        ordering = ["project_name"]

    def __str__(self):
        return self.project_name


class StackComponent(TimeStampedModel):
    project = models.ForeignKey(Project, related_name="components", on_delete=models.CASCADE)
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
    
    class Meta:
        unique_together = [['project', 'library']]
        ordering = ['-updated_at']
        verbose_name = 'Update Cache'
        verbose_name_plural = 'Update Caches'

    def __str__(self):
        return f"{self.project.project_name} :: {self.library} -> {self.version} ({self.category})"



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
    
    class Meta:
        ordering = ['-confidence', '-updated_at']
        unique_together = [['library', 'version']]
        verbose_name = 'Future Update'
        verbose_name_plural = 'Future Updates'
    
    def __str__(self):
        return f"{self.library} {self.version} (future, {self.confidence}% confidence)"
