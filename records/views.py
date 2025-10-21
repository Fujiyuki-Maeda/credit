import csv
import io
from datetime import date, datetime

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, UpdateView

from .forms import CSVUploadForm, RecordEditForm, VoucherCountForm
from .models import Card, DailyCheck, ImportBatch, Record, VoucherCount
from django.http import JsonResponse

# カードのコードと名前の対応表を定義
CARD_MAP = {
    '1': 'クレジット', '2': 'ALIPAY', '3': 'PayPay', '4': 'LINE Pay', '5': '交通系電子マネー',
    '6': '銀聯', '7': 'Edy', '8': 'WAON', '9': 'nanaco', '10': 'QUICPay',
    '11': 'ID', '12': 'd払い', '15': 'アマゾン', '16': 'ヤフオク', '17': 'ルーチェ',
    '18': '携帯業者売り', '19': '自販機売上', '20': '金券売上', '21': '金プラ売上',
    '22': 'ガチャ売上', '23': '買取当番', '25': '楽天市場', '26': 'QR決済',
    '27': 'BISTY', '28': 'その他売上',
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

            new_batch = ImportBatch.objects.create()
            success_count = 0
            skipped_count = 0

            for row in reader:
                slip_number_val = ""
                try:
                    # ▼▼▼ この3行を追記 ▼▼▼
                    # H列（インデックス7）の「区分」をチェック
                    slip_division = row[7]
                    if slip_division in ['取消', '赤伝']:
                        continue # この行の処理をスキップして次の行へ
                    # ▲▲▲ 追記ここまで ▲▲▲

                    slip_number_val = row[8]
                    if not slip_number_val:
                        continue

                    card_code = row[2]
                    card_name = CARD_MAP.get(card_code, card_code)
                    card_obj, _ = Card.objects.get_or_create(name=card_name)

                    naive_datetime = datetime.strptime(row[5], "%Y/%m/%d %H:%M:%S")
                    aware_datetime = timezone.make_aware(naive_datetime)

                    payment_type_value = None
                    if card_name != 'クレジット':
                        payment_type_value = card_name

                    Record.objects.create(
                        batch=new_batch,
                        store_code=row[0],
                        store_name=row[1],
                        card=card_obj,
                        transaction_datetime=aware_datetime,
                        slip_type=row[6],
                        slip_number=slip_number_val,
                        payment_type=payment_type_value,
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
                except (ValueError, IndexError):
                    messages.warning(request, f"伝票番号 '{slip_number_val}' の行は形式が不正なためスキップされました。")
                    skipped_count += 1

            if success_count == 0:
                new_batch.delete()

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

    def post(self, request, *args, **kwargs):
        for key, value in request.POST.items():
            if key.startswith('receipt_amount_'):
                record_id = int(key.split('_')[2])
                try:
                    record = Record.objects.get(pk=record_id)
                    record.receipt_amount = int(value) if value else None
                    record.save()
                except Record.DoesNotExist:
                    continue
        messages.success(request, 'レシート金額を保存しました。')
        return redirect('records:record_list')

# ▼▼▼ 新しい「直前のインポートを取り消す」機能 ▼▼▼
class UndoLastImportView(View):
    def get(self, request, *args, **kwargs):
        last_batch = ImportBatch.objects.order_by('-timestamp').first()
        context = {'last_batch': last_batch}
        return render(request, 'records/undo_last_import_confirm.html', context)

    def post(self, request, *args, **kwargs):
        last_batch = ImportBatch.objects.order_by('-timestamp').first()
        if last_batch:
            last_batch.delete()
            messages.success(request, '直前のインポート処理を取り消しました。')
        else:
            messages.warning(request, '取り消すインポート処理がありません。')
        return redirect('records:record_list')

def summary_view(request):
    target_date_str = request.GET.get('date', date.today().strftime('%Y-%m-%d'))
    target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()

    # --- 保存処理 (POST) ---
    if request.method == 'POST':
        card_id = request.POST.get('card_id')
        if card_id: # ポップアップからの保存リクエストの場合
            pos_total_1 = request.POST.get('pos_total_1')
            pos_total_2 = request.POST.get('pos_total_2')
            pos_total_3 = request.POST.get('pos_total_3')

            card_instance = Card.objects.get(id=card_id)
            DailyCheck.objects.update_or_create(
                date=target_date,
                card=card_instance,
                defaults={
                    'pos_total_1': pos_total_1,
                    'pos_total_2': pos_total_2,
                    'pos_total_3': pos_total_3,
                }
            )
            return JsonResponse({'status': 'success'})

        # --- 金券枚数の個別保存処理 ---
        for time, _ in VoucherCount.CHECK_TIMES:
            button_name = f'save_voucher_{time}'
            if button_name in request.POST:
                count_value = request.POST.get(f'{time}-count')
                if count_value:
                    VoucherCount.objects.update_or_create(
                        date=target_date, check_time=time,
                        defaults={'count': int(count_value)}
                    )
                    messages.success(request, f"{target_date} {time} の金券枚数を保存しました。")
                else:
                    VoucherCount.objects.filter(date=target_date, check_time=time).delete()
                    messages.info(request, f"{target_date} {time} の金券枚数をクリアしました。")
                break

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

    saved_checks = DailyCheck.objects.filter(date=target_date)
    saved_checks_dict = {check.card_id: check for check in saved_checks}

    for summary_item in summary_data_list:
        card_id = summary_item['card_id']
        check_obj = saved_checks_dict.get(card_id)
        if check_obj:
            t1_str = check_obj.pos_total_1 or "0"
            t2_str = check_obj.pos_total_2 or "0"
            t3_str = check_obj.pos_total_3 or "0"
            try:
                # 'eval' is used to calculate strings like '1000+500'
                total = eval(t1_str) + eval(t2_str) + eval(t3_str)
            except:
                total = 0
            summary_item.update({
                'pos_total_1': t1_str, 'pos_total_2': t2_str, 'pos_total_3': t3_str,
                'pos_total_sum': total
            })
        else:
            summary_item.update({
                'pos_total_1': '', 'pos_total_2': '', 'pos_total_3': '',
                'pos_total_sum': ''
            })

    # ▼▼▼ 前回省略してしまっていた金券フォームの準備処理 ▼▼▼
    voucher_forms = []
    for time, label in VoucherCount.CHECK_TIMES:
        instance = VoucherCount.objects.filter(date=target_date, check_time=time).first()
        form = VoucherCountForm(instance=instance, prefix=time)
        voucher_forms.append({'label': label, 'form': form})

    total_vouchers = VoucherCount.objects.filter(date=target_date).aggregate(Sum('count'))['count__sum'] or 0
    # ▲▲▲ ここまで ▲▲▲

    context = {
        'summary_data': summary_data_list,
        'target_date': target_date,
        'voucher_forms': voucher_forms,
        'total_vouchers': total_vouchers,
    }
    return render(request, 'records/summary.html', context)

class RecordUpdateView(UpdateView):
    model = Record
    form_class = RecordEditForm
    template_name = 'records/record_form.html'
    success_url = reverse_lazy('records:record_list')

def export_csv(request):
    if request.method == 'POST':
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')

        if not start_date or not end_date:
            messages.error(request, '開始日と終了日を両方選択してください。')
            return redirect('records:export_csv')

        records_in_range = Record.objects.filter(
            transaction_datetime__date__range=[start_date, end_date]
        )

        if records_in_range.filter(Q(payment_type=None) | Q(payment_type='')).exists():
            messages.warning(request, f'期間内に支払い区分が「未選択」のデータがあります。')
            return redirect('records:export_csv')

        if records_in_range.filter(receipt_amount=None).exists():
            messages.warning(request, f'期間内にレシート金額が未入力のデータがあります。全てのレシート金額を入力してください。')
            return redirect('records:export_csv')

        if records_in_range.exclude(receipt_amount=F('payment_amount')).exists():
            messages.warning(request, f'期間内に支払金額とレシート金額が一致しないデータがあります。赤いハイライトの行を確認してください。')
            return redirect('records:export_csv')

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
    else:
        return render(request, 'records/export_form.html')

def monthly_report_view(request):
    today = date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    dates_queryset = Record.objects.dates('transaction_datetime', 'year')
    available_years = sorted([d.year for d in dates_queryset], reverse=True)
    available_months = range(1, 13)

    summary_data = Record.objects.filter(
        transaction_datetime__year=year,
        transaction_datetime__month=month
    ).values('card__name').annotate(
        total_amount=Sum('payment_amount'), total_count=Count('id')
    ).order_by('-total_amount')

    chart_labels = [item['card__name'] for item in summary_data]
    chart_data = [item['total_amount'] for item in summary_data]

    context = {
        'summary_data': summary_data, 'selected_year': year, 'selected_month': month,
        'available_years': available_years, 'available_months': available_months,
        'chart_labels': chart_labels, 'chart_data': chart_data,
    }
    return render(request, 'records/monthly_report.html', context)