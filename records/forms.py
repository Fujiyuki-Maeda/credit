from django import forms
from .models import Record
from .models import VoucherCount

class CSVUploadForm(forms.Form):
    file = forms.FileField(
        label="CSVファイル",
        help_text="レジPOSからダウンロードしたクレジット利用履歴.csvを選択してください"
    )

class RecordEditForm(forms.ModelForm):
    # ▼▼▼ ここのリストに「分割」が含まれているかご確認ください ▼▼▼
    PAYMENT_TYPE_CHOICES = [
        ('', '---------'),
        ('JCB/一括', 'JCB/一括'),
        ('JCB/リボ', 'JCB/リボ'),
        ('JCB/ボーナス', 'JCB/ボーナス'),
        ('JCB/分割', 'JCB/分割'),      # JCB/分割
        ('VISA/一括', 'VISA/一括'),
        ('VISA/リボ', 'VISA/リボ'),
        ('VISA/ボーナス', 'VISA/ボーナス'),
        ('VISA/分割', 'VISA/分割'),      # VISA/分割
    ]
    
    payment_type = forms.ChoiceField(
        choices=PAYMENT_TYPE_CHOICES, 
        required=False, 
        label="支払い区分",
        widget=forms.Select(attrs={'id': 'payment_type_select'})
    )
    
    installments = forms.IntegerField(
        required=False, 
        label="分割回数",
        widget=forms.NumberInput(attrs={'id': 'installments_input'})
    )

    class Meta:
        model = Record
        fields = ['payment_type', 'installments']
        
class VoucherCountForm(forms.ModelForm):
    class Meta:
        model = VoucherCount
        fields = ['count']
        widgets = {
            'count': forms.NumberInput(attrs={'class': 'form-control', 'style': 'width: 100px;'})
        }
        labels = {
            'count': '' # ラベルは表示しない
        }