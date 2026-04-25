"""URL config for Django admin."""
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import path


def root(request):
    return HttpResponseRedirect("admin/")


urlpatterns = [
    path("", root),
    path("admin/", admin.site.urls),
]

admin.site.site_header = "Job Hunt Agent — Admin"
admin.site.site_title = "Job Hunt Admin"
admin.site.index_title = "Operational Dashboard"
