# credit_card_manager/urls.py

from django.contrib import admin
# include をインポートします
from django.urls import path, include 

urlpatterns = [
    path('admin/', admin.site.urls),
    # この行を追加します
    path('', include('records.urls')),
]