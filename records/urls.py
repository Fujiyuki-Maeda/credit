# records/urls.py

from django.urls import path
from . import views

app_name = 'records'

urlpatterns = [
    # 一覧ページとインポートページだけを残します
    path('', views.RecordListView.as_view(), name='record_list'),
    path('import/', views.import_csv, name='import_csv'),
    path('delete-all/', views.DeleteAllRecordsView.as_view(), name='delete_all'),
    path('summary/', views.summary_view, name='summary'),
    path('edit/<int:pk>/', views.RecordUpdateView.as_view(), name='record_edit'),
    path('export/', views.export_csv, name='export_csv'),
    path('monthly/', views.monthly_report_view, name='monthly_report'),
]