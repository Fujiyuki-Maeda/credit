# records/models.py

from django.db import models
from django.utils import timezone

# マスタデータ：カード会社を名前で管理します
class Card(models.Model):
    name = models.CharField("カード会社名", max_length=100, unique=True)

    def __str__(self):
        return self.name

# メインのデータ：CSVの1行がこのレコード1つに相当します
class Record(models.Model):
    # --- CSVの列に対応するフィールド ---
    store_code = models.CharField("店舗コード", max_length=50, null=True, blank=True)
    store_name = models.CharField("店舗名称", max_length=100)
    
    card = models.ForeignKey(Card, on_delete=models.PROTECT, verbose_name="カード会社")
    
    transaction_datetime = models.DateTimeField("操作日時", default=timezone.now)
    
    slip_type = models.CharField("伝票区分", max_length=50, null=True, blank=True)
    
    # 伝票番号は重複がないキーとして設定
    slip_number = models.CharField("伝票番号", max_length=50, unique=True)
    
    # 金額に関するフィールド (DecimalFieldで正確に扱います)
    total_amount = models.DecimalField("合計金額(J列)", max_digits=10, decimal_places=0, default=0)
    discount_amount = models.DecimalField("割引金額", max_digits=10, decimal_places=0, default=0)
    cash_payment = models.DecimalField("現金支払", max_digits=10, decimal_places=0, default=0)
    voucher_payment = models.DecimalField("金券支払", max_digits=10, decimal_places=0, default=0)
    voucher_count = models.IntegerField("金券枚数", default=0)
    points_used = models.DecimalField("利用ポイント", max_digits=10, decimal_places=0, default=0)
    payment_amount = models.DecimalField("支払(P列)", max_digits=10, decimal_places=0, default=0)
    card_payment_type = models.CharField("カード会社支払い区分(S列)", max_length=100, null=True, blank=True)
    payment_type = models.CharField("支払い区分", max_length=50, null=True, blank=True)
    installments = models.IntegerField("分割回数", null=True, blank=True) # 分割払い以外は空になる

    # --- アプリケーションで管理する追加情報 ---
    created_at = models.DateTimeField("作成日", auto_now_add=True)
    updated_at = models.DateTimeField("更新日", auto_now=True)

    class Meta:
        ordering = ['-transaction_datetime'] # 日時の新しい順に並べる

    def __str__(self):
        return f"{self.transaction_datetime.strftime('%Y-%m-%d')} - {self.store_name} (¥{self.payment_amount})"
    
class DailyCheck(models.Model):
    """日次照合の結果を保存するモデル"""
    date = models.DateField("日付")
    card = models.ForeignKey(Card, on_delete=models.CASCADE, verbose_name="カード会社")
    pos_total = models.DecimalField("レジ合計金額", max_digits=10, decimal_places=0)

    class Meta:
        # 同じ日に同じカード会社のデータが重複しないように設定
        unique_together = ('date', 'card')

    def __str__(self):
        return f"{self.date} - {self.card.name}: {self.pos_total}"
    
class VoucherCount(models.Model):
    """点検時間ごとの金券枚数を保存するモデル"""
    CHECK_TIMES = [
        ('13:10', '13:10'),
        ('17:10', '17:10'),
        ('21:30', '21:30'),
    ]
    date = models.DateField("日付")
    check_time = models.CharField("点検時間", max_length=5, choices=CHECK_TIMES)
    count = models.IntegerField("枚数")

    class Meta:
        # 同じ日に同じ時間のデータが重複しないように設定
        unique_together = ('date', 'check_time')

    def __str__(self):
        return f"{self.date} {self.check_time} - {self.count}枚"