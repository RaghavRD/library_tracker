from django.db import models

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


class UpdateCache(models.Model):
    library = models.CharField(max_length=200, unique=True)
    version = models.CharField(max_length=100)
    release_date = models.CharField(max_length=50, blank=True)
    category = models.CharField(max_length=10, choices=UPDATE_CATEGORY_CHOICES)
    summary = models.TextField(blank=True)
    source = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.library} -> {self.version} ({self.category})"
