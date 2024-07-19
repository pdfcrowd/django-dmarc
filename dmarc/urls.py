#----------------------------------------------------------------------
# Copyright (c) 2015-2021, Persistent Objects Ltd https://p-o.co.uk/
#
# License: BSD
#----------------------------------------------------------------------
"""
DMARC urls
http://dmarc.org/resources/specification/
"""
from django.urls import re_path
from dmarc import views

app_name = 'dmarc'
urlpatterns = [
    re_path("^report/$", views.dmarc_report, name='dmarc_report'),
    re_path("^report/csv/$", views.dmarc_csv, name='dmarc_csv'),
    re_path("^report/json/$", views.dmarc_json, name='dmarc_json'),
]
