from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/tracker/dashboard/", permanent=False)),
    path("tracker/", include("tracker.urls")),
]

# handler404 = "tracker.views.page_not_found"
# handler500 = "tracker.views.server_error"

# if "debug_toolbar" in settings.INSTALLED_APPS:
#     import debug_toolbar

#     urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]

# if settings.DEBUG:
#     from django.conf.urls.static import static

#     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    