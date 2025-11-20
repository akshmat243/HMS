import uuid
from django.db import models
from django.utils.text import slugify
from django.utils import timezone
from ckeditor.fields import RichTextField
from django.contrib.auth import get_user_model

User = get_user_model()

class Page(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True, editable=False)
    template = models.CharField(max_length=100, default='default.html')
    content = RichTextField(blank=True)
    is_published = models.BooleanField(default=False)
    publish_date = models.DateTimeField(null=True, blank=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='pages')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            count = 1
            while Page.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{count}"
                count += 1
            self.slug = slug

        if self.is_published and not self.publish_date:
            self.publish_date = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_published', 'publish_date']),
        ]



class FAQ(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)  # New
    answer = models.TextField()
    category = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.question)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.question


class Banner(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, blank=True)  # New
    image = models.ImageField(upload_to='cms/banners/')
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    link = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class MetaTag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.OneToOneField(Page, on_delete=models.CASCADE, related_name='meta_tags')
    slug = models.SlugField(unique=True, blank=True)  # New
    meta_title = models.CharField(max_length=255)
    meta_description = models.TextField()
    keywords = models.TextField(help_text="Comma-separated keywords")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.meta_title)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Meta: {self.page.title}"

from django.db import models
from django.utils.text import slugify

class SidebarApp(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=60, unique=True, blank=True)
    label = models.CharField(max_length=100)
    icon = models.CharField(max_length=100, blank=True)
    route = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    group = models.CharField(max_length=50, blank=True)
    # Role-based field: list of allowed role names
    roles_allowed = models.TextField(
        blank=True,
        help_text='Comma separated role names allowed to access this module.'
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            new_slug = base_slug
            counter = 1
            while SidebarApp.objects.filter(slug=new_slug).exclude(id=self.id).exists():
                new_slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = new_slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.label

