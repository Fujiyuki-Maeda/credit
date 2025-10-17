# records/admin.py

from django.contrib import admin
from .models import Card, Record

# Cardモデルを管理画面に登録
@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

# Recordモデルを管理画面に登録
@admin.register(Record)
class RecordAdmin(admin.ModelAdmin):
    # 一覧画面に表示するフィールド
    list_display = ('transaction_datetime', 'store_name', 'card', 'slip_number', 'payment_amount')
    # 絞り込み（フィルター）に使うフィールド
    list_filter = ('transaction_datetime', 'card', 'store_name')
    # 検索ボックスで検索対象にするフィールド
    search_fields = ('store_name', 'slip_number')
    # 日付での絞り込みを可能にする
    date_hierarchy = 'transaction_datetime'