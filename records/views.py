# records/views.py

import csv
import io
from datetime import datetime
from django.utils import timezone
from django.urls import reverse_lazy
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import IntegrityError
from django.views.generic import ListView, UpdateView
from .models import DailyCheck
from django.views import View

from .forms import CSVUploadForm
from .models import Record, Card

from django.db.models import Sum, Count
from datetime import date
from .forms import RecordEditForm # 後で作成するフォームをインポート
import csv
from django.http import HttpResponse
from django.db.models import Q

from .models import VoucherCount
from .forms import VoucherCountForm
from django.db.models.functions import TruncMonth

# カードのコードと名前の対応表を定義
CARD_MAP = {
    '1': 'クレジット',
    '10': 'QUICPay',
    '11': 'ID',
    '26': 'QR決済',
    # 今後新しいコードが増えたらここに追加します
}

def import_csv(request):
    if request.method == 'POST':
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['file']
            try:
                decoded_file = csv_file.read().decode('cp932')
            except UnicodeDecodeError:
                messages.error(request, "ファイルの文字コードが合いません。CSVファイルをShift-JIS (cp932) 形式で保存し直してください。")
                return redirect('records:import_csv')

            io_string = io.StringIO(decoded_file)
            reader = csv.reader(io_string)
            next(reader, None)

            success_count = 0
            skipped_count = 0

            for row in reader:
                slip_number_val = ""
                try:
                    slip_number_val = row[8]
                    if not slip_number_val:
                        continue
                    
                    card_code = row[2]
                    card_name = CARD_MAP.get(card_code, card_code)
                    card_obj, _ = Card.objects.get_or_create(name=card_name)
                    
                    naive_datetime = datetime.strptime(row[5], "%Y/%m/%d %H:%M:%S")
                    aware_datetime = timezone.make_aware(naive_datetime)

                    # ▼▼▼ 変更点 ▼▼▼
                    # カード会社が 'クレジット' でなければ、支払い区分にカード会社名を自動でセット
                    payment_type_value = None  # デフォルトは空 (未選択)
                    if card_name != 'クレジット':
                        payment_type_value = card_name
                    # ▲▲▲ 変更ここまで ▲▲▲

                    Record.objects.create(
                        store_code=row[0],
                        store_name=row[1],
                        card=card_obj,
                        transaction_datetime=aware_datetime,
                        slip_type=row[6],
                        slip_number=slip_number_val,
                        payment_type=payment_type_value, # 💡 作成した変数を使う
                        total_amount=row[9] or 0,
                        discount_amount=row[10] or 0,
                        cash_payment=row[11] or 0,
                        voucher_payment=row[12] or 0,
                        voucher_count=row[13] or 0,
                        points_used=row[14] or 0,
                        payment_amount=row[15] or 0,
                        card_payment_type=row[18] if len(row) > 18 else "",
                    )
                    success_count += 1

                except IntegrityError:
                    skipped_count += 1
                except (ValueError, IndexError) as e:
                    messages.warning(request, f"伝票番号 '{slip_number_val}' の行は形式が不正なためスキップされました。")
                    skipped_count += 1

            messages.success(request, f"{success_count}件の新しいデータがインポートされました。({skipped_count}件は重複または不正な形式のためスキップ)")
            return redirect('records:record_list')
    else:
        form = CSVUploadForm()

    return render(request, 'records/import_csv.html', {'form': form})


class RecordListView(ListView):
    model = Record
    template_name = 'records/record_list.html'
    paginate_by = 50

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_count'] = Record.objects.count()
        return context


class DeleteAllRecordsView(View):
    def get(self, request, *args, **kwargs):
        # 確認ページを表示
        return render(request, 'records/delete_all_confirm.html')

    def post(self, request, *args, **kwargs):
        # 全てのレコードを削除
        Record.objects.all().delete()
        messages.success(request, '全ての利用履歴が削除されました。')
        return redirect('records:record_list')
    
def summary_view(request):
    target_date_str = request.GET.get('date', date.today().strftime('%Y-%m-%d'))
    target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()

    if request.method == 'POST':
        # --- クレジット合計の保存処理 ---
        if 'save_pos_total' in request.POST:
            for key, value in request.POST.items():
                if key.startswith('pos_total_'):
                    card_id = int(key.split('_')[2])
                    if value:
                        pos_amount = int(value)
                        card_instance = Card.objects.get(id=card_id)
                        DailyCheck.objects.update_or_create(
                            date=target_date,
                            card=card_instance,
                            defaults={'pos_total': pos_amount}
                        )
            messages.success(request, f"{target_date}のレジ合計金額を保存しました。")
        
        # ▼▼▼ 変更点 ▼▼▼
        # --- 金券枚数の個別保存処理 ---
        # どの時間帯の保存ボタンが押されたかチェック
        for time, _ in VoucherCount.CHECK_TIMES:
            button_name = f'save_voucher_{time}'
            if button_name in request.POST:
                count_value = request.POST.get(f'{time}-count')
                # 値が空でない場合のみ保存・更新
                if count_value:
                    VoucherCount.objects.update_or_create(
                        date=target_date,
                        check_time=time,
                        defaults={'count': int(count_value)}
                    )
                    messages.success(request, f"{target_date} {time} の金券枚数を保存しました。")
                else: # もし入力欄が空で保存が押されたら、データを削除する
                    VoucherCount.objects.filter(date=target_date, check_time=time).delete()
                    messages.info(request, f"{target_date} {time} の金券枚数をクリアしました。")
                break # 該当するボタンを見つけたらループを抜ける
        # ▲▲▲ 変更ここまで ▲▲▲

        return redirect(f"{request.path}?date={target_date_str}")

    # --- 表示処理 (GET) ---
    summary_data_list = list(Record.objects.filter(
        transaction_datetime__date=target_date
    ).values(
        'card_id', 'card__name'
    ).annotate(
        total_amount=Sum('payment_amount'),
        total_count=Count('id')
    ).order_by('card__name'))
    
    saved_checks_queryset = DailyCheck.objects.filter(date=target_date)
    saved_checks_dict = {check.card_id: check.pos_total for check in saved_checks_queryset}

    for summary_item in summary_data_list:
        card_id = summary_item['card_id']
        summary_item['pos_total'] = saved_checks_dict.get(card_id, '')

    voucher_forms = []
    for time, label in VoucherCount.CHECK_TIMES:
        instance = VoucherCount.objects.filter(date=target_date, check_time=time).first()
        form = VoucherCountForm(instance=instance, prefix=time)
        voucher_forms.append({'label': label, 'form': form})
    
    total_vouchers = VoucherCount.objects.filter(date=target_date).aggregate(Sum('count'))['count__sum'] or 0

    context = {
        'summary_data': summary_data_list,
        'target_date': target_date,
        'voucher_forms': voucher_forms,
        'total_vouchers': total_vouchers,
    }
    return render(request, 'records/summary.html', context)

class RecordUpdateView(UpdateView):
    model = Record
    form_class = RecordEditForm # カスタムフォームを使用
    template_name = 'records/record_form.html'
    success_url = reverse_lazy('records:record_list')
    
def export_csv(request):
    # 支払い区分が未選択または空のデータが存在するかチェック
    unselected_exists = Record.objects.filter(
        Q(payment_type=None) | Q(payment_type='')
    ).exists()

    # もし未選択のデータが1件でもあれば、警告を出して処理を中断
    if unselected_exists:
        messages.warning(request, '支払い区分が「未選択」のデータがあります。全ての区分を選択してから再度エクスポートしてください。')
        return redirect('records:record_list')

    # 未選択のデータがなければ、通常通りCSVを作成
    response = HttpResponse(content_type='text/csv', charset='cp932')
    response['Content-Disposition'] = 'attachment; filename="keiri_data.csv"'

    writer = csv.writer(response)
    writer.writerow(['伝票日付', 'カード会社支払い区分', '金額'])
    
    records_to_export = Record.objects.all().order_by('transaction_datetime')

    for record in records_to_export:
        # ▼▼▼ 変更点 ▼▼▼
        # 分割回数が存在するかどうかで、出力する文字列を動的に作成する
        payment_type_display = record.payment_type
        if record.installments:
            payment_type_display = f"{record.payment_type} ({record.installments}回)"
        # ▲▲▲ 変更ここまで ▲▲▲

        writer.writerow([
            record.transaction_datetime.strftime('%Y/%m/%d'),
            payment_type_display,  # 💡 作成した変数を使う
            record.payment_amount
        ])

    return response

def monthly_report_view(request):
    # 現在の年・月を取得
    today = date.today()
    # GETパラメータから年・月を取得、なければ現在の年月を使う
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    # 正しい方法で、データベースに記録されている年の一覧を取得する
    dates_queryset = Record.objects.dates('transaction_datetime', 'year')
    available_years = sorted([d.year for d in dates_queryset], reverse=True)

    # ▼▼▼ 変更点 ▼▼▼
    # 月の選択肢 (1から12) をここで準備する
    available_months = range(1, 13)
    # ▲▲▲ 変更ここまで ▲▲▲

    # 選択された年・月でデータを絞り込み、カード会社ごとに集計
    summary_data = Record.objects.filter(
        transaction_datetime__year=year,
        transaction_datetime__month=month
    ).values(
        'card__name'
    ).annotate(
        total_amount=Sum('payment_amount'),
        total_count=Count('id')
    ).order_by('-total_amount')

    # --- グラフ用のデータを作成 ---
    chart_labels = [item['card__name'] for item in summary_data]
    chart_data = [item['total_amount'] for item in summary_data]

    context = {
        'summary_data': summary_data,
        'selected_year': year,
        'selected_month': month,
        'available_years': available_years,
        'available_months': available_months, # 💡 作成した月のリストをcontextに追加
        'chart_labels': chart_labels,
        'chart_data': chart_data,
    }
    return render(request, 'records/monthly_report.html', context)