"""Deterministic Persian report text; no translation API costs."""
import re
FA = {
'purchase price':'قیمت خرید','minimum size':'حداقل مساحت','search radius':'شعاع جستجو','loan limit':'سقف وام','price per m²':'قیمت هر متر مربع','rental yield':'بازده اجاره','monthly result':'نتیجه ماهانه','financing data missing':'اطلاعات مالی ناقص','ownership type':'نوع مالکیت','auction status':'وضعیت مزایده','location unverified':'موقعیت تأیید نشده','ownership or auction status unknown':'نوع مالکیت یا وضعیت مزایده نامشخص',
'unknown':'نامشخص','unknown: rent, financing or owner costs missing':'نامشخص؛ اجاره، تأمین مالی یا هزینه مالک ناقص است','advertised':'طبق آگهی','actual':'طبق آگهی','estimate':'برآوردی','estimated':'برآوردی',
'🏠 Apartment screening':'🏠 بررسی آپارتمان‌ها','Data last researched: ':'آخرین تاریخ تحقیق: ',
'Gross rental yield is before costs, not profit.':'بازده ناخالص اجاره قبل از هزینه‌هاست و به معنی سود خالص نیست.',
'No candidates within known limits. Main blockers: ':'گزینه‌ای مطابق محدودیت‌های قابل بررسی یافت نشد. دلایل اصلی: ',
'insufficient verified listings':'تعداد ناکافی آگهی تأییدشده','🔄 If you are flexible':'🔄 اگر کمی انعطاف داشته باشید','from ':'از ',
' · distance unverified':' · فاصله تأیید نشده','📈 Gross rental yield: ':'📈 بازده ناخالص اجاره: ',' before costs':' قبل از هزینه‌ها',
'🏦 Estimated loan needed: ':'🏦 وام مورد نیاز برآوردی: ','💵 Cold rent: ':'💵 اجاره خالص: ','/month':' در ماه',
'🗓 Annual rental income: ':'🗓 درآمد سالانه اجاره: ','🏷 Purchase price: ':'🏷 قیمت خرید: ',
'💳 Estimated mortgage payment: ':'💳 قسط وام برآوردی: ','💰 Estimated monthly result: ':'💰 نتیجه ماهانه برآوردی: ',
'🌧 If interest rates rise: ':'🌧 در سناریوی افزایش نرخ بهره: ','🏢 Owner building fees: ':'🏢 هزینه ساختمان سهم مالک: ',
' (reserve contributions excluded)':' (بدون پرداخت به ذخیره ساختمان)','🛠 Maintenance allowance: ':'🛠 ذخیره برآوردی تعمیرات: ',
'🏗 Built: ':'🏗 سال ساخت: ','Energy: ':'رده انرژی: ','⭐ Screening score: ':'⭐ امتیاز بررسی: ','💬 Verdict: ':'💬 ارزیابی: ',
'Rent covers estimated costs.':'اجاره هزینه‌های برآوردشده را پوشش می‌دهد.','Needs extra money or cost clarification.':'نیازمند پرداخت اضافی یا روشن شدن هزینه‌هاست.',
'⚠️ Provisional candidate — not checked: ':'⚠️ گزینه موقت؛ موارد بررسی‌نشده: ',
'. Confirm missing details with the seller; your exclusions still apply.':'. اطلاعات ناقص را از فروشنده بپرسید؛ موارد مستثناشده شما همچنان اعمال می‌شود.',
'🔎 Monthly subtotal before missing purchase costs: ':'🔎 نتیجه ماهانه موقت پیش از هزینه‌های خرید نامشخص: ',
'⚠️ Partial calculation excludes unknown ':'⚠️ محاسبه ناقص است؛ این هزینه نامشخص لحاظ نشده: ',
'. Loan and payments may be higher; financing is not confirmed.':'. وام و اقساط واقعی ممکن است بیشتر باشد؛ تأمین مالی تأیید نشده است.',
'🔎 Before unknown owner fees: ':'🔎 پیش از هزینه‌های نامشخص مالک: ',
' (maintenance already included; final result unknown).':' (ذخیره تعمیرات لحاظ شده؛ نتیجه نهایی نامشخص است).',
'🧾 Purchase costs used: ':'🧾 هزینه‌های خرید لحاظ‌شده: ','transfer tax':'مالیات انتقال ملک','notary/registry':'دفتر اسناد رسمی و ثبت ملک','buyer commission':'کمیسیون خریدار',
'Transfer tax: official state rate, verified 2026-10-04. ':'مالیات انتقال ملک: نرخ رسمی ایالت، بررسی‌شده در ۲۰۲۶/۱۰/۰۴. ',
'Estimate basis: ':'مبنای برآورد: ','Loan unknown: buyer commission or state tax missing.':'وام نامشخص؛ کمیسیون خریدار یا مالیات ایالت ناقص است.',
'Area average comparison: ':'مقایسه با میانگین منطقه: ',' (not a property valuation). ':' (ارزش‌گذاری این ملک نیست). ',
'Previously shown; still in the saved pool.':'قبلاً نمایش داده شده؛ همچنان در داده‌های ذخیره‌شده موجود است.',
'Outside your limits; required changes: ':'خارج از محدودیت‌های شما؛ تغییرات لازم: ',
'Not financeable under your current loan cap.':'با سقف وام فعلی شما قابل تأمین مالی نیست.',
'⚠️ Main risk: ':'⚠️ ریسک اصلی (متن منبع): ','🔗 Listing: ':'🔗 آگهی: ',
'💶 MORTGAGE RATES':'💶 نرخ‌های وام مسکن','As of ':'تا تاریخ ',
'📊 Nominal interest range: ':'📊 دامنه نرخ بهره اسمی: ','🧮 Payment estimate uses: ':'🧮 مبنای برآورد قسط: ',
'🌧 Stress scenario: ':'🌧 سناریوی فشار: ',' nominal · dated ':' اسمی · تاریخ ',
' interest; this is not a change during an agreed fixed-rate period.':' بهره؛ این سناریو به معنی تغییر نرخ در دوره ثابت قراردادی نیست.',
'✅ Source dates are no more than 14 days old.':'✅ تاریخ منابع حداکثر مربوط به ۱۴ روز گذشته است.',
'⚠️ Financing unknown: two recent nominal-rate sources unavailable.':'⚠️ تأمین مالی نامشخص؛ دو منبع جدید برای نرخ اسمی در دسترس نیست.',
'📋 STILL TO CHECK':'📋 موارد نیازمند بررسی',
'Ask sellers to confirm ownership type, auction status, lease, owner-only building fees and planned major repairs.':'از فروشنده درباره نوع مالکیت، مزایده، قرارداد اجاره، هزینه‌های سهم مالک و تعمیرات عمده برنامه‌ریزی‌شده سؤال کنید.',
'⚠️ Estimates include ~2% notary/registry and €1/m² monthly maintenance. Distances use approximate town centers. Taxes on income, empty months and major repairs are excluded. Check leases, building repair plans, rent controls and availability. Zero-equity financing is not guaranteed. Scores use a fixed screening rubric, not predictions.':'⚠️ برآورد شامل حدود ۲٪ هزینه دفتر اسناد و ثبت ملک و ماهانه ۱ یورو به ازای هر متر مربع برای تعمیرات است. فاصله از مرکز تقریبی شهر محاسبه می‌شود. مالیات درآمد، دوره بدون مستأجر و تعمیرات عمده لحاظ نشده است. قرارداد اجاره، برنامه تعمیرات، محدودیت اجاره و موجود بودن ملک را بررسی کنید. تأمین مالی بدون آورده تضمین‌شده نیست. امتیازها معیار غربالگری هستند، نه پیش‌بینی.',
'Estimates only; general information, not financial advice or a financing commitment. Verify independently before deciding.':'صرفاً برآورد و اطلاعات عمومی است؛ مشاوره مالی یا تعهد تأمین مالی نیست. پیش از تصمیم‌گیری، مستقل بررسی کنید.',
'⚠️ Partial research — no confirmed investment recommendations':'⚠️ تحقیق ناقص؛ هیچ توصیه سرمایه‌گذاری تأییدشده‌ای ارائه نشده است',
'Last researched: ':'آخرین تاریخ تحقیق: ','Location/radius could not be fully verified. Your limits have not been changed.':'موقعیت یا شعاع کاملاً تأیید نشده است. محدودیت‌های شما تغییر نکرده‌اند.',
'🔎 Research lead only; eligibility and financing are not verified.':'🔎 صرفاً سرنخ تحقیق است؛ انطباق با معیارها و تأمین مالی تأیید نشده است.',
'⚠️ Partial research: only fully extracted, verified data was retained.\n\n':'⚠️ تحقیق ناقص؛ فقط داده‌های استخراج‌شده و تأییدشده حفظ شده است.\n\n',
}
def fa(text):
    if text in FA: return FA[text]
    patterns=[
        (r'(\d+) researched apartments available; search coverage is limited.',lambda m:f'{m[1]} آپارتمان بررسی‌شده موجود است؛ پوشش جستجو محدود است.'),
        (r'(\d+) candidates within known limits; (\d+) nearby alternatives.',lambda m:f'{m[1]} گزینه مطابق محدودیت‌های قابل بررسی؛ {m[2]} گزینه جایگزین نزدیک.'),
        (r'(\d+)-year fixed',lambda m:f'نرخ ثابت {m[1]} ساله'),
        (r' interest \+ ([\d.]+)% initial repayment',lambda m:f' بهره + {m[1]}٪ بازپرداخت اولیه سالانه'),
        (r'/month (left|extra needed)',lambda m:' در ماه '+('مازاد' if m[1]=='left' else 'پرداخت اضافی لازم')),
    ]
    for pattern,render in patterns:
        match=re.fullmatch(pattern,text)
        if match: return render(match)
    return text
