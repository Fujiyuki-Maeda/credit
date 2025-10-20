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
from django.db.models import Q, F

from .models import VoucherCount
from .forms import VoucherCountForm
from django.db.models.functions import TruncMonth

# カードのコードと名前の対応表を定義
CARD_MAP = {
    '1': 'クレジット',
    '2': 'ALIPAY',
    '3': 'PayPay',
    '4': 'LINE Pay',
    '5': '交通系電子マネー',
    '6': '銀聯',
    '7': 'Edy',
    '8': 'WAON',
    '9': 'nanaco',
    '10': 'QUICPay',
    '11': 'ID',
    '12': 'd払い',
    '15': 'アマゾン',
    '16': 'ヤフオク',
    '17': 'ルーチェ',
    '18': '携帯業者売り',
    '19': '自販機売上',
    '20': '金券売上',
    '21': '金プラ売上',
    '22': 'ガチャ売上',
    '23': '買取当番',
    '25': '楽天市場',
    '26': 'QR決済',
    '27': 'BISTY',
    '28': 'その他売上',
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

    # ▼▼▼ この post メソッドを追記 ▼▼▼
    def post(self, request, *args, **kwargs):
        # フォームから送信されたデータをループ処理
        for key, value in request.POST.items():
            # 'receipt_amount_{id}' という名前の入力欄を探す
            if key.startswith('receipt_amount_'):
                record_id = int(key.split('_')[2])
                try:
                    record = Record.objects.get(pk=record_id)
                    # 入力値が空でなければ、金額として保存
                    if value:
                        record.receipt_amount = int(value)
                    # 入力値が空なら、None (空) として保存
                    else:
                        record.receipt_amount = None
                    record.save()
                except Record.DoesNotExist:
                    # 該当するレコードが見つからない場合は何もしない
                    continue

        messages.success(request, 'レシート金額を保存しました。')
        # 同じページにリダイレクトして再表示
        return redirect('records:record_list')


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
    if request.method == 'POST':
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')

        if not start_date or not end_date:
            messages.error(request, '開始日と終了日を両方選択してください。')
            return redirect('records:export_csv')

        # 指定された期間のデータを取得
        records_in_range = Record.objects.filter(
            transaction_datetime__date__range=[start_date, end_date]
        )

        # --- ▼▼▼ 新しいチェックロジック ▼▼▼ ---

        # チェック1: 支払い区分が未選択のデータがないか？
        if records_in_range.filter(Q(payment_type=None) | Q(payment_type='')).exists():
            messages.warning(request, f'期間内に支払い区分が「未選択」のデータがあります。')
            return redirect('records:export_csv')

        # チェック2: レシート金額が未入力のデータがないか？
        if records_in_range.filter(receipt_amount=None).exists():
            messages.warning(request, f'期間内にレシート金額が未入力のデータがあります。全てのレシート金額を入力してください。')
            return redirect('records:export_csv')

        # チェック3: 支払金額とレシート金額が一致しないデータがないか？
        if records_in_range.exclude(receipt_amount=F('payment_amount')).exists():
            messages.warning(request, f'期間内に支払金額とレシート金額が一致しないデータがあります。赤いハイライトの行を確認してください。')
            return redirect('records:export_csv')

        # --- ▲▲▲ チェックロジックここまで ▲▲▲ ---

        # 全てのチェックをパスした場合のみ、CSVを作成
        response = HttpResponse(content_type='text/csv', charset='cp932')
        response['Content-Disposition'] = f'attachment; filename="keiri_data_{start_date}_to_{end_date}.csv"'

        writer = csv.writer(response)
        writer.writerow(['伝票日付', 'カード会社支払い区分', '金額'])

        for record in records_in_range.order_by('transaction_datetime'):
            payment_type_display = record.payment_type
            if record.installments:
                payment_type_display = f"{record.payment_type} ({record.installments}回)"

            writer.writerow([
                record.transaction_datetime.strftime('%Y/%m/%d'),
                payment_type_display,
                record.payment_amount
            ])

        return response

    else: # GETリクエストの場合
        return render(request, 'records/export_form.html')

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