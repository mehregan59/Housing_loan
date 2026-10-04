// Short webhook only: long OpenAI work runs in GitHub Actions.
const env = (key: string) => { const v = Deno.env.get(key); if (!v) throw new Error('Missing configuration'); return v; };
const NOTICE = 'Estimates only; general information, not financial advice or a financing commitment. Verify independently before deciding. Listing data may be incomplete. Settings and reports are stored in Supabase; analysis uses OpenAI; Telegram delivers messages. API costs are reported to the administrator. Do not send bank credentials or identity documents. /support forwards your message and Telegram ID to the administrator. This is a private pilot, not a publicly launched service.';
const HELP = `Housing Loan Bot — Germany pilot
/start — read notice and accept
/guide — step-by-step setup before your first analysis
/settings — your investment settings; tap buttons to edit each field
/cancel — cancel the current edit
/set FIELD VALUE — change one setting
Example: /set max_price_eur 250000
/location Freiburg — choose a German city
/areas Freiburg, Emmendingen — preferred towns
/exclude Erbpacht, Zwangsversteigerung — exclusions; "none" clears
/schedule mon 08:00 Europe/Berlin — day, time, timezone
/weekly on or /weekly off — automatic report
/run — analysis using saved research where available
/refresh — administrator only: paid search for additional apartments within the spending cap
/quota — weekly allowance
/last — latest saved report
/saved — existing report for your exact settings; no quota or AI cost
/support YOUR QUESTION — contact the administrator
/disclaimer — notice and data use
/buy — one report or a 30-day weekly pass when payments open
/terms — purchase terms
/paysupport YOUR QUESTION — payment help
Pilot users remain free. Paid checkout uses Telegram Stars; euro cost varies.
Free: 1 report/week. Paid: up to 7. Scheduled reports count too. Reset Monday 00:00 Europe/Berlin. Manual membership during pilot. Delivery may be delayed; changing schedule does not add reports. If a report fails, use /support; repeated clicks cannot start parallel analyses.
Editable numeric fields: max_loan_eur, equity_eur, max_price_eur, min_size_m2, radius_km, max_price_per_m2, target_gross_yield_pct, min_monthly_cashflow_eur, fixed_rate_years, repayment_pct. Optional targets accept "none". /set language en, de or fa. Other countries will require country-specific rules in a future release.`;
const HELP_FA=`راهنمای ربات مسکن — آلمان
/guide — راهنمای گام‌به‌گام قبل از اولین تحلیل
/settings — تنظیمات؛ برای تغییر هر مورد دکمه را بزنید
/set language fa — گزارش فارسی
/set language en — گزارش انگلیسی
/set language de — گزارش آلمانی
/location Freiburg — انتخاب شهر آلمان
/areas Freiburg, Emmendingen — شهرهای ترجیحی
/set max_price_eur 250000 — حداکثر قیمت خرید
/set max_loan_eur 250000 — سقف وام
/set equity_eur 0 — آورده نقدی
/set min_size_m2 30 — حداقل مساحت
/set radius_km 100 — شعاع جستجو
/run — بررسی با استفاده از داده‌های ذخیره‌شده در صورت موجود بودن
/saved — گزارش ذخیره‌شده بدون هزینه جدید
/last — آخرین گزارش
/weekly on یا /weekly off — گزارش هفتگی
/schedule mon 08:00 Europe/Berlin — زمان گزارش
/quota — سهمیه هفتگی
/support متن سؤال — ارسال سؤال به پشتیبانی
/cancel — لغو ویرایش
/refresh — فقط مدیر؛ جستجوی پولی برای آگهی‌های بیشتر در سقف بودجه
طرح رایگان یک گزارش و طرح پولی تا هفت گزارش در هفته دارد. گزارش‌ها فقط برآورد هستند، نه مشاوره مالی یا تأیید وام. عنوان آگهی و متن ریسک منبع ممکن است به زبان اصلی باقی بماند.`;
const CALCULATIONS_EN=`🧮 How the estimates work
📈 Gross rental yield (%) = monthly cold rent × 12 ÷ purchase price × 100. This is rental income before costs, not profit.
🏦 Loan needed = purchase price + state transfer tax + estimated 2% notary/registry + stated buyer commission − equity; never less than zero. Zero means your stated equity covers these purchase costs, not that a bank approved financing.
💳 Monthly mortgage payment ≈ loan × (annual nominal interest % + initial annual repayment %) ÷ 1200. This is an initial annuity estimate; the fixed-rate period does not mean the loan is repaid in full during that period.
💰 Monthly result = cold rent − mortgage payment − owner-only operating building fees − maintenance allowance (€1/m² per month). Building reserve contributions are excluded from owner fees to avoid counting maintenance twice.
🌧 Stress payment uses the highest sourced rate + 1 percentage point, with the same repayment. It is a scenario, not an increase during a contractual fixed-rate period.
📐 Price per m² = purchase price ÷ apartment size.
Missing required inputs → “Missing data”, not zero. Other available criteria can still be checked; open Details for unchecked limits. A verified state tax rate may fill a missing tax field. Estimates must name their source/basis.
Income tax, vacancy, letting costs and major unexpected repairs are excluded. Scores are a screening rubric, not predictions; incomplete rent/cashflow data is not rated. Rates & assumptions opens the report sources. Apartment links open saved details; Back to list returns to the overview without a new AI call.`;
const CALCULATIONS_FA=`🧮 روش محاسبه برآوردها
📈 بازده ناخالص اجاره (%) = اجاره خالص ماهانه × ۱۲ ÷ قیمت خرید × ۱۰۰. این درآمد پیش از هزینه‌هاست، نه سود خالص.
🏦 وام مورد نیاز = قیمت خرید + مالیات انتقال ملک ایالت + حدود ۲٪ دفتر اسناد و ثبت ملک + کمیسیون خریدار − آورده نقدی. نتیجه کمتر از صفر نمی‌شود. صفر یعنی آورده اعلام‌شده هزینه خرید را پوشش می‌دهد؛ تأیید وام از بانک نیست.
💳 قسط ماهانه ≈ وام × (درصد بهره اسمی سالانه + درصد بازپرداخت اولیه سالانه) ÷ ۱۲۰۰. این برآورد قسط اولیه است؛ دوره نرخ ثابت به معنی تسویه کامل وام در همان دوره نیست.
💰 نتیجه ماهانه = اجاره خالص − قسط وام − هزینه‌های جاری ساختمان سهم مالک − ذخیره تعمیرات (ماهانه ۱ یورو برای هر متر مربع). پرداخت به ذخیره ساختمان از هزینه‌های سهم مالک حذف می‌شود تا تعمیرات دوبار حساب نشود.
🌧 سناریوی فشار: بالاترین نرخ منبع + یک واحد درصد، با همان بازپرداخت. این به معنی تغییر نرخ در دوره ثابت قراردادی نیست.
📐 قیمت هر متر مربع = قیمت خرید ÷ مساحت.
اگر ورودی لازم موجود نباشد، «اطلاعات ناقص» نمایش داده می‌شود، نه صفر. بقیه معیارهای موجود بررسی می‌شوند؛ موارد بررسی‌نشده در جزئیات مشخص است. نرخ رسمی مالیات ایالت می‌تواند جای اطلاعات مالیاتی ناقص را بگیرد. برآوردها باید منبع و مبنای مشخص داشته باشند.
مالیات درآمد، دوره بدون مستأجر، هزینه اجاره دادن و تعمیرات عمده غیرمنتظره لحاظ نشده است. امتیازها پیش‌بینی نیستند؛ با اطلاعات ناقص اجاره یا جریان نقدی امتیاز داده نمی‌شود. پیوند جزئیات اطلاعات ذخیره‌شده را باز می‌کند؛ بازگشت به فهرست هیچ درخواست جدید هوش مصنوعی ندارد.`;
const CALCULATIONS_DE=`🧮 Berechnung der Schätzungen
Bruttomietrendite (%) = monatliche Kaltmiete × 12 ÷ Kaufpreis × 100; vor Kosten, kein Gewinn.
Kreditbedarf = Kaufpreis + Grunderwerbsteuer des Landes + ca. 2% Notar/Grundbuch + Käuferprovision − Eigenkapital, mindestens null. Null bedeutet ausreichendes angegebenes Eigenkapital, keine Bankzusage.
Monatliche Rate ≈ Kredit × (Sollzins % + anfängliche jährliche Tilgung %) ÷ 1200. Die Zinsbindung ist nicht die vollständige Rückzahlungsdauer.
Monatsergebnis = Kaltmiete − Rate − nicht umlagefähige laufende Eigentümerkosten − 1 €/m² monatliche Instandhaltung. Rücklagenzahlungen werden aus Eigentümerkosten herausgerechnet, um Doppelzählung zu vermeiden.
Stresstest: höchster Quellenzins + 1 Prozentpunkt; keine Zinsänderung während der vereinbarten Bindung. €/m² = Kaufpreis ÷ Wohnfläche.
Fehlende notwendige Werte → „Fehlende Daten“, niemals null Euro. Verfügbare Kriterien werden weiterhin geprüft; ungeprüfte Grenzen stehen unter Details. Amtlich bestätigte Landessteuer kann fehlende Steuerangaben ergänzen.
Einkommensteuer, Leerstand, Vermietungskosten und größere unerwartete Reparaturen fehlen. Daten zu Miete/Cashflow unvollständig → keine Bewertung. Details und Zurück zur Liste verwenden gespeicherte Daten ohne neuen KI-Aufruf.`;
const MAX: Record<string, [number, number]> = {
  max_loan_eur:[0,10000000],equity_eur:[0,10000000],max_price_eur:[1,10000000],
  min_size_m2:[1,2000],radius_km:[1,500],max_price_per_m2:[1,100000],
  target_gross_yield_pct:[0,100],min_monthly_cashflow_eur:[-100000,100000],
  fixed_rate_years:[1,40],repayment_pct:[0,30]
};
const OPTIONAL = new Set(['max_price_per_m2','target_gross_yield_pct','min_monthly_cashflow_eur']);

const DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const LABELS: Record<string,string> = {
  location:'City', areas:'Preferred towns', radius_km:'Search radius',
  max_price_eur:'Maximum purchase price',max_loan_eur:'Maximum loan',equity_eur:'Available equity',
  min_size_m2:'Minimum size',language:'Report language',fixed_rate_years:'Fixed interest period',
  repayment_pct:'Initial annual repayment',max_price_per_m2:'Maximum price per m²',
  target_gross_yield_pct:'Target gross rental yield',min_monthly_cashflow_eur:'Minimum monthly cashflow',
  schedule_time:'Delivery time',timezone:'Timezone'
};
const GROUPS: Record<string,string[]> = {
  search:['location','areas','radius_km','max_price_eur','min_size_m2','language'],
  finance:['max_loan_eur','equity_eur','fixed_rate_years','repayment_pct'],
  targets:['max_price_per_m2','target_gross_yield_pct','min_monthly_cashflow_eur'],
  schedule:['schedule_time','timezone']
};
const button=(text:string,data:string)=>({text,callback_data:data});
const money=(v:unknown)=>new Intl.NumberFormat('en-GB',{style:'currency',currency:'EUR',maximumFractionDigits:2}).format(Number(v));
export function settingsSummary(u:any):string {
  const s=u.settings;
  if (s.language==='fa') {
    const option=(key:string,unit:string)=>s[key]==null?'بدون محدودیت':unit==='EUR'?money(s[key]):s[key]+unit;
    return `🏠 تنظیمات جستجوی ملک
📍 ${s.location}، آلمان · شعاع ${s.radius_km} کیلومتر
شهرهای ترجیحی: ${(s.areas||[]).join(', ')||'بدون ترجیح اضافی'}
💶 حداکثر قیمت خرید: ${money(s.max_price_eur)}
📐 حداقل مساحت: ${s.min_size_m2} متر مربع
🌐 زبان گزارش: فارسی

🏦 فرض‌های تأمین مالی
حداکثر وام: ${money(s.max_loan_eur)}
آورده نقدی: ${money(s.equity_eur)}
دوره نرخ ثابت: ${s.fixed_rate_years} سال
بازپرداخت اولیه سالانه: ${s.repayment_pct==null?'نامشخص':s.repayment_pct+'%'}

🎯 معیارهای سرمایه‌گذاری
حداکثر قیمت هر متر مربع: ${option('max_price_per_m2','EUR')}
بازده ناخالص اجاره: ${option('target_gross_yield_pct','%')}
حداقل نتیجه ماهانه: ${option('min_monthly_cashflow_eur','EUR')}
🚫 موارد مستثنا: ${(s.exclude||[]).map((x:string)=>x==='Erbpacht'?'ملک با حق اجاره زمین':x==='Zwangsversteigerung'?'مزایده توقیفی':x).join('، ')||'هیچ‌کدام'}
📅 گزارش هفتگی: ${u.weekly?'روشن':'خاموش'}
زمان: ${DAYS[u.schedule_day]}، ${u.schedule_time} · ${u.timezone}
طرح: ${u.admin_unlimited?'مدیر؛ بدون سقف هفتگی':u.payments_active?'پرداخت هر گزارش / بسته هفتگی ۳۰ روزه':u.pilot_free?'آزمایشی؛ بدون پرداخت':u.plan==='paid'?'اشتراک پولی؛ تا ۷ گزارش در هفته':'رایگان؛ یک گزارش در هفته'}
برای تغییر تنظیمات دکمه‌های زیر را بزنید. هزینه‌های خرید در محاسبه وام لحاظ می‌شود؛ این تنظیمات تأیید تأمین مالی نیست.`;
  }
  const optional=(key:string,unit:string)=>s[key]==null?'No filter set':unit==='EUR'?money(s[key]):s[key]+unit;
  const exclusions=(s.exclude||[]).map((x:string)=>x==='Erbpacht'?'Leasehold':x==='Zwangsversteigerung'?'Foreclosure auctions':x).join(', ')||'None';
  return `🏠 Your property search
📍 ${s.location}, Germany · within ${s.radius_km} km
Preferred towns: ${(s.areas||[]).join(', ')||'No additional preference'}
💶 Maximum purchase price: ${money(s.max_price_eur)}
📐 Minimum size: ${s.min_size_m2} m²
🌐 Report language: ${s.language==='fa'?'فارسی':s.language==='de'?'German':'English'}

🏦 Financing assumptions
Maximum loan: ${money(s.max_loan_eur)}
Available equity: ${money(s.equity_eur)}
Fixed interest period: ${s.fixed_rate_years} years
Initial annual repayment: ${s.repayment_pct==null?'Not set — mortgage payment unavailable':s.repayment_pct+'%'}

🎯 Investment targets
Maximum price per m²: ${optional('max_price_per_m2','EUR')}
Gross rental yield: ${optional('target_gross_yield_pct','%')}
Monthly cashflow: ${optional('min_monthly_cashflow_eur','EUR')}

🚫 Excluded: ${exclusions}

📅 Weekly reports: ${u.weekly?'On':'Off'}
Schedule: ${DAYS[u.schedule_day]}, ${u.schedule_time} · ${u.timezone}
Plan: ${u.admin_unlimited?'Administrator — no weekly report limit':u.payments_active?'Pay per report / optional 30-day weekly pass':u.pilot_free?'Pilot — no payment required':u.plan==='paid'?'Paid — up to 7 reports/week':'Free — 1 report/week'}

${u.pilot_locked?'🔒 Pilot settings are fixed for all users. Weekly reports: Monday 09:00 Europe/Berlin.':'Tap a button below to edit.'} Purchase costs count toward your loan limit. These are preferences, not a financing approval.`;
}
const settingsButtons={inline_keyboard:[
  [button('🔎 Edit search','menu:search'),button('🏦 Edit financing','menu:finance')],
  [button('🎯 Investment targets','menu:targets'),button('🚫 Exclusions','menu:exclude')],
  [button('📅 Change schedule','menu:schedule')],
  [button('🔎 Run analysis','run'),button('❓ Help','help')],
  [button('📖 Continue guide','guide:resume')]
]};
export function setupGuide(step:number,language:string,user:any) {
  const fa=language==='fa',de=language==='de';
  const t=(en:string,ger:string,per:string)=>fa?per:de?ger:en;
  const lessons=[
    t('📖 1/7 — Start here\nThis bot screens German apartments for rental investment. Reports are estimates, not financing approval or advice. It searches a limited set of public adverts, not every apartment on the market. Settings, help and opening saved details do not cost AI money.\nChoose your report language below, then Next. You can return with /guide at any time.',
      '📖 1/7 — Einstieg\nDer Bot prüft deutsche Wohnungen zur Vermietung. Berichte sind Schätzungen, keine Finanzierungszusage oder Beratung. Die Suche ist eine begrenzte Stichprobe, kein vollständiger Marktbestand. Einstellungen, Hilfe und gespeicherte Details verursachen keine KI-Kosten.\nSprache wählen, dann Weiter. /guide öffnet diese Anleitung erneut.',
      '📖 ۱/۷ — شروع\nاین ربات آپارتمان‌های آلمان را برای سرمایه‌گذاری اجاره‌ای بررسی می‌کند. گزارش برآورد است، نه تأیید وام یا مشاوره. جستجو نمونه‌ای محدود از آگهی‌هاست، نه همه املاک بازار. تنظیمات، راهنما و جزئیات ذخیره‌شده هزینه هوش مصنوعی ندارند.\nزبان گزارش را انتخاب کنید و سپس «بعدی» را بزنید. /guide راهنما را دوباره باز می‌کند.'),
    t('📍 2/7 — Choose your search\nCity is the search centre; radius is approximate straight-line distance in km. Preferred towns help ordering; they do not exclude every other town. Set maximum purchase price and minimum apartment size.\nTap Edit search, choose a field, type its new value and send it. Changes save immediately. /cancel stops an edit. Return using Continue guide.',
      '📍 2/7 — Suche festlegen\nDie Stadt ist das Suchzentrum; der Radius ist die ungefähre Luftlinie in km. Bevorzugte Orte beeinflussen die Reihenfolge, sind kein Ausschluss anderer Orte. Maximalen Kaufpreis und Mindestfläche setzen.\nSuche bearbeiten → Feld wählen → neuen Wert senden. Änderungen werden sofort gespeichert. /cancel bricht ab; Anleitung fortsetzen führt zurück.',
      '📍 ۲/۷ — محدوده جستجو\nشهر مرکز جستجوست؛ شعاع فاصله تقریبی مستقیم به کیلومتر است. شهرهای ترجیحی ترتیب نمایش را تغییر می‌دهند و سایر شهرها را حذف نمی‌کنند. حداکثر قیمت خرید و حداقل مساحت را تعیین کنید.\n«ویرایش جستجو» → انتخاب مورد → ارسال مقدار جدید. تغییر فوراً ذخیره می‌شود. /cancel ویرایش را لغو می‌کند؛ با «ادامه راهنما» برگردید.'),
    t('🏦 3/7 — Set your financing\nMaximum loan is how much you are willing to borrow, not the property price. Equity is cash you can contribute. Loan need includes purchase costs. Fixed-rate years describe interest fixation, not full repayment duration. Repayment % is the initial annual repayment.\nExample: /set equity_eur 30000. Enter your real amounts before running; broad test settings can produce unrealistic choices.',
      '🏦 3/7 — Finanzierung\nDie Kreditgrenze ist Ihr gewünschter Höchstkredit, nicht der Kaufpreis. Eigenkapital ist verfügbares Bargeld. Kreditbedarf enthält Kaufnebenkosten. Zinsbindung ist nicht die gesamte Rückzahlungsdauer; Tilgung % ist die anfängliche jährliche Tilgung.\nBeispiel: /set equity_eur 30000. Vor dem Start echte Werte statt breiter Testwerte verwenden.',
      '🏦 ۳/۷ — تأمین مالی\nسقف وام حداکثر مبلغی است که می‌خواهید قرض بگیرید، نه قیمت ملک. آورده پول نقد قابل استفاده شماست. وام مورد نیاز شامل هزینه‌های خرید است. دوره نرخ ثابت زمان ثابت بودن بهره است، نه زمان تسویه کامل وام. درصد بازپرداخت، بازپرداخت اولیه سالانه است.\nمثال: /set equity_eur 30000. قبل از اجرا مقادیر واقعی خود را جایگزین تنظیمات آزمایشی گسترده کنید.'),
    t('🎯 4/7 — Optional investment targets\nPrice per m² compares purchase price with size. Gross rental yield is annual cold rent ÷ price × 100, before costs. Monthly cashflow subtracts payment, owner fees and maintenance from cold rent. Positive cashflow is not guaranteed.\nYou can leave targets off; /set target_gross_yield_pct none clears a target. Strict targets reduce results. Confirmed exclusions remain excluded; missing details are flagged for seller checks.',
      '🎯 4/7 — Optionale Ziele\n€/m² = Kaufpreis ÷ Fläche. Bruttorendite = Jahreskaltmiete ÷ Kaufpreis × 100, vor Kosten. Cashflow zieht Rate, Eigentümerkosten und Instandhaltung von der Kaltmiete ab. Positiver Cashflow ist nicht garantiert.\nZiele können aus bleiben: /set target_gross_yield_pct none. Strenge Ziele reduzieren Treffer. Bestätigte Ausschlüsse gelten; fehlende Angaben müssen beim Verkäufer geprüft werden.',
      '🎯 ۴/۷ — معیارهای اختیاری\nقیمت هر متر مربع = قیمت خرید ÷ مساحت. بازده ناخالص = اجاره خالص سالانه ÷ قیمت خرید × ۱۰۰، پیش از هزینه‌ها. نتیجه ماهانه از اجاره، قسط، هزینه‌های مالک و ذخیره تعمیرات را کم می‌کند. جریان نقدی مثبت تضمین نشده است.\nمی‌توانید معیارها را خاموش بگذارید؛ /set target_gross_yield_pct none معیار را پاک می‌کند. معیارهای سخت‌گیرانه نتایج را کم می‌کنند. موارد مستثنای تأییدشده حذف می‌شوند؛ اطلاعات ناقص را از فروشنده بپرسید.'),
    t('🔎 5/7 — Read a report\nThe short list shows price, size, rent, loan/payment and yield. Tap Details for full stored information, Listing for the seller advert, and Back to list to return. Rates & assumptions shows dated sources. These links do not start analysis.\n“Missing data” means a calculation cannot be completed; it is not zero. Estimated figures are labelled with their basis. /help explains every formula. All retained candidates are sent across report pages; the search itself is not exhaustive.',
      '🔎 5/7 — Bericht lesen\nDie Übersicht zeigt Preis, Fläche, Miete, Kredit/Rate und Rendite. Details öffnet gespeicherte Angaben; Anzeige öffnet das Inserat. Zurück zur Liste führt zur Übersicht; Zinsen & Annahmen zeigt Quellen. Diese Links starten keine Analyse.\n„Fehlende Daten“ ist kein Nullwert. Schätzungen nennen ihre Grundlage. /help erklärt Formeln. Alle gespeicherten passenden Angebote werden über Seiten angezeigt; die Recherche ist nicht vollständig.',
      '🔎 ۵/۷ — خواندن گزارش\nفهرست کوتاه قیمت، مساحت، اجاره، وام/قسط و بازده را نشان می‌دهد. «جزئیات» اطلاعات ذخیره‌شده و «آگهی» صفحه فروشنده را باز می‌کند؛ «بازگشت به فهرست» شما را برمی‌گرداند. بخش نرخ بهره و فرض‌ها منابع تاریخ‌دار را نشان می‌دهد. این پیوندها تحلیل جدید شروع نمی‌کنند.\n«اطلاعات ناقص» یعنی محاسبه کامل ممکن نیست، نه صفر. ارقام برآوردی مبنای مشخص دارند. /help فرمول‌ها را توضیح می‌دهد. همه گزینه‌های ذخیره‌شده مطابق معیارها در صفحات نمایش داده می‌شوند؛ جستجو کامل نیست.'),
    t('📅 6/7 — Delivery and allowance\nWeekly reports start off. Set your day, time and timezone first, then enable weekly delivery if wanted. /weekly off stops scheduled reports. Free members get one report/week; paid members up to seven. Scheduled reports count too. Settings changes do not increase the allowance.\n/run reuses research when available. /saved and /last retrieve stored reports for free. Only the administrator can /refresh for additional paid research. Wait for a running job; repeated clicks cannot start a second one.',
      '📅 6/7 — Versand und Kontingent\nWöchentliche Berichte sind anfangs aus. Erst Tag, Uhrzeit und Zeitzone setzen, dann bei Bedarf aktivieren. /weekly off beendet geplante Berichte. Kostenlos: ein Bericht/Woche; bezahlt: bis sieben. Geplante Berichte zählen mit. Einstellungen ändern erhöht das Kontingent nicht.\n/run nutzt vorhandene Recherche; /saved und /last sind kostenlos. Nur der Administrator kann mit /refresh zusätzlich recherchieren. Während eines laufenden Auftrags warten.',
      '📅 ۶/۷ — زمان‌بندی و سهمیه\nگزارش هفتگی ابتدا خاموش است. روز، ساعت و منطقه زمانی را تعیین کنید و در صورت تمایل فعال کنید. /weekly off گزارش خودکار را متوقف می‌کند. طرح رایگان یک و طرح پولی تا هفت گزارش در هفته دارد؛ گزارش خودکار هم حساب می‌شود. تغییر تنظیمات سهمیه را بیشتر نمی‌کند.\n/run در صورت وجود از تحقیق ذخیره‌شده استفاده می‌کند. /saved و /last رایگان هستند. فقط مدیر با /refresh تحقیق پولی بیشتری انجام می‌دهد. تا پایان کار در حال اجرا صبر کنید.'),
    t('✅ 7/7 — Review, then start\nReview your current settings below. Tap Review settings to make changes and Continue guide to return. Run analysis uses these saved settings and may consume your weekly allowance or require new research. It will reuse existing research where possible.\nNo analysis runs merely by reading this guide. If ready, tap Run with my settings. Questions: /support YOUR QUESTION.',
      '✅ 7/7 — Prüfen, dann starten\nAktuelle Einstellungen unten prüfen. Einstellungen prüfen öffnet Änderungen; Anleitung fortsetzen führt zurück. Analyse starten verwendet diese Werte und kann Kontingent oder neue Recherche benötigen; vorhandene Daten werden wiederverwendet.\nDas Lesen startet nichts. Bei Bereitschaft Analyse starten wählen. Fragen: /support IHRE FRAGE.',
      '✅ ۷/۷ — بررسی و شروع\nتنظیمات فعلی را در زیر بررسی کنید. «بررسی تنظیمات» برای تغییر و «ادامه راهنما» برای بازگشت است. اجرای تحلیل از این تنظیمات استفاده می‌کند و ممکن است سهمیه مصرف کند یا تحقیق جدید لازم داشته باشد؛ داده موجود در صورت امکان دوباره استفاده می‌شود.\nخواندن راهنما هیچ تحلیلی شروع نمی‌کند. اگر آماده‌اید «اجرا با تنظیمات من» را بزنید. سؤال: /support متن سؤال')
  ];
  if(user.payments_active) lessons[5]='📅 6/7 — Purchases and weekly delivery\n'+PAYMENT_GUIDE;
  if(!Number.isSafeInteger(step)||step<0||step>=lessons.length) throw new Error('Invalid guide step');
  const rows:any[][]=[];
  if(step===0) rows.push([button('English','lang:en'),button('Deutsch','lang:de'),button('فارسی','lang:fa')]);
  if(step===1) rows.push([button(t('Edit search','Suche bearbeiten','ویرایش جستجو'),'menu:search')]);
  if(step===2) rows.push([button(t('Edit financing','Finanzierung bearbeiten','ویرایش تأمین مالی'),'menu:finance')]);
  if(step===3) rows.push([button(t('Edit targets','Ziele bearbeiten','ویرایش معیارها'),'menu:targets'),button(t('Exclusions','Ausschlüsse','موارد مستثنا'),'menu:exclude')]);
  if(step===4) rows.push([button(t('Formulas and help','Formeln und Hilfe','فرمول‌ها و راهنما'),'help')]);
  if(step===5) rows.push([button(t('Edit schedule','Zeitplan bearbeiten','ویرایش زمان‌بندی'),'menu:schedule')]);
  if(step===6) rows.push([button(t('Review settings','Einstellungen prüfen','بررسی تنظیمات'),'settings'),button(t('I understand — finish setup','Verstanden — Einrichtung abschließen','متوجه شدم — پایان تنظیمات'),'guide:complete')]);
  const navigation=[];
  if(step) navigation.push(button(t('← Previous','← Zurück','← قبلی'),'guide:'+(step-1)));
  if(step<6) navigation.push(button(t('Next →','Weiter →','بعدی →'),'guide:'+(step+1)));
  if(navigation.length) rows.push(navigation);
  return {text:lessons[step]+(step===6?'\n\n'+settingsSummary(user):''),keyboard:{inline_keyboard:rows}};
}

export function parseEdit(field:string,input:string):unknown {
  let value=input.trim();
  if (['location','areas'].includes(field)) {
    if (!value || value.length>(field==='location'?100:500)) throw new Error('Enter a city name or a short list of towns.');
    return field==='location'?value:value.toLowerCase()==='none'?[]:value.split(',').map(x=>x.trim()).filter(Boolean).slice(0,15);
  }
  if (field==='language') { if (!['en','de','fa'].includes(value)) throw new Error('Choose English, German or Persian below.'); return value; }
  if (field==='timezone') { try { new Intl.DateTimeFormat('en',{timeZone:value}).format(); } catch { throw new Error('Enter a timezone such as Europe/Berlin.'); } return value; }
  if (field==='schedule_time') {
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(value)) throw new Error('Enter a 24-hour time, for example 08:00 or 18:30.');
    return value;
  }
  if (OPTIONAL.has(field) && value.toLowerCase()==='none') return null;
  // Accept 250000, 250 000, 250,000, 250.000, €250,000 and decimal comma percentages.
  value=value.replace(/[€%\s]/g,'').replace(/(?:km|m²|m2|years?)$/i,'');
  if (/^-?\d{1,3}(?:[,.]\d{3})+$/.test(value)) value=value.replace(/[,.]/g,'');
  else if (/^-?\d+,\d{1,2}$/.test(value)) value=value.replace(',','.');
  if (!/^-?\d+(?:\.\d+)?$/.test(value)) throw new Error('Enter a number, for example 250000 or 2.5.');
  const n=Number(value), bounds=MAX[field];
  if (!bounds || !Number.isFinite(n) || n<bounds[0] || n>bounds[1] || (field==='fixed_rate_years'&&!Number.isInteger(n))) {
    throw new Error(bounds?`Enter a value from ${bounds[0]} to ${bounds[1]}${field==='fixed_rate_years'?' in whole years':''}.`:'Unknown setting.');
  }
  return n;
}
function editPrompt(field:string):string {
  const examples:Record<string,string>={location:'Freiburg (Germany only)',areas:'Freiburg, Emmendingen — or none',radius_km:'100',max_price_eur:'250000',
    max_loan_eur:'250000',equity_eur:'0',min_size_m2:'30',fixed_rate_years:'10',repayment_pct:'2',
    max_price_per_m2:'5000',target_gross_yield_pct:'4',min_monthly_cashflow_eur:'-150',schedule_time:'08:00',timezone:'Europe/Berlin'};
  return `${LABELS[field]}\nSend the new value in your next message.\nExample: ${examples[field]||'en or de'}${OPTIONAL.has(field)?'\nSend none to remove this filter.':''}\nUse /cancel to leave without changing it.`;
}

async function db(method: string, path: string, body?: unknown, timeout=10000) {
  const key = Deno.env.get('BOT_DATABASE_KEY') || env('SUPABASE_SERVICE_ROLE_KEY');
  const r = await fetch(env('SUPABASE_URL')+'/rest/v1/'+path, {
    method, headers:{apikey:key,'Content-Type':'application/json',Prefer:'return=representation'},
    body:body === undefined ? undefined : JSON.stringify(body), signal:AbortSignal.timeout(timeout)
  });
  if (!r.ok) throw new Error('Database operation failed');
  return r.status === 204 ? null : await r.json();
}
async function tg(method: string, body: unknown) {
  const r = await fetch('https://api.telegram.org/bot'+env('TELEGRAM_BOT_TOKEN')+'/'+method, {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(10000)
  });
  if (!r.ok || !(await r.json()).ok) throw new Error('Telegram operation failed');
}
async function reply(id: number, text: string, keyboard?: unknown, entities?: any[]) {
  let first = true;let offset=0;
  while (text.length) {
    let cut = Math.min(text.length,3800);
    // JavaScript counts UTF-16 units: never cut between an emoji's surrogates.
    if (cut < text.length) {
      const before = text.charCodeAt(cut-1);
      if (before >= 0xD800 && before <= 0xDBFF) cut--;
      const boundary = text.lastIndexOf('\n',cut-1);
      if (boundary >= Math.floor(cut/2)) cut = boundary+1;
    }
    const local=(entities||[]).flatMap(e=>{const start=Math.max(offset,e.offset),end=Math.min(offset+cut,e.offset+e.length);return start<end?[{...e,offset:start-offset,length:end-start}]:[];});
    await tg('sendMessage',{chat_id:id,text:text.slice(0,cut),link_preview_options:{is_disabled:true},
      ...(keyboard && first ? {reply_markup:keyboard} : {}),...(local.length?{entities:local}:{})});
    offset+=cut;first = false;
    text = text.slice(cut);
  }
}

export function splitReport(report:string) {
  const headings=[...report.matchAll(/^((?:🏠 — |🔄[^\n]* — ).*)$/gm)];
  if (!headings.length) return {header:report,cards:[] as {detail:string;brief:string;url:string}[],notes:''};
  let notesStart=report.indexOf('\n💶 ',headings.at(-1)!.index!+headings.at(-1)![0].length);
  if(notesStart<0) notesStart=report.length;
  const cards=[];
  for(let i=0;i<headings.length;i++) {
    const detail=report.slice(headings[i].index,i+1<headings.length?headings[i+1].index:notesStart).trim();
    const lines=detail.split('\n');
    const urls=lines.at(-1)!.match(/https?:\/\/\S+/g);
    if(!urls) return {header:report,cards:[],notes:''};
    const brief=[lines[0],...['📍','🏷','📐','💵','🏦','💳','📈'].flatMap(p=>lines.filter(l=>l.startsWith(p)))].join('\n');
    cards.push({detail,brief,url:urls.at(-1)!});
  }
  return {header:report.slice(0,headings[0].index).trim(),cards,notes:report.slice(notesStart).trim()};
}
function reportLabels(language:string) {
  return language==='fa'?['جزئیات','آگهی','نرخ بهره و فرض‌ها','صفحه','⬆️ بازگشت به فهرست']:language==='de'?['Details','Anzeige','Zinsen & Annahmen','Seite','⬆️ Zurück zur Liste']:['Details','Listing','Rates & assumptions','Page','⬆️ Back to list'];
}
function reportLink(source:string,kind:string,index?:number) {
  const username=Deno.env.get('TELEGRAM_BOT_USERNAME')||'MeHousingLoanBot';
  const payload=kind+'_'+source+(index===undefined?'':'_'+index);
  if(!/^[A-Za-z0-9_]+$/.test(username)||payload.length>64||!/^[A-Za-z0-9_-]+$/.test(payload)) throw new Error('Invalid report link');
  return 'https://t.me/'+username+'?start='+payload;
}
function addReportLink(text:string,entities:any[],label:string,url:string) {
  entities.push({type:'text_link',offset:text.length,length:label.length,url});
  return text+label;
}
export function reportPage(view:ReturnType<typeof splitReport>,source:string,index:number,language:string) {
  const [details,listing,notes,pageLabel]=reportLabels(language);
  const total=Math.ceil(view.cards.length/5);
  if(!Number.isSafeInteger(index)||index<0||index>=total) throw new Error('Invalid report page');
  let text=view.header+'\n'+`${pageLabel} ${index+1}/${total}`;
  const entities:any[]=[];
  for(let i=index*5;i<Math.min((index+1)*5,view.cards.length);i++) {
    const card=view.cards[i];text+=`\n\n${i+1}. `+card.brief.replace(/^🏠 — /,'')+' · ';
    text=addReportLink(text,entities,details,reportLink(source,'prop',i))+' · ';
    text=addReportLink(text,entities,listing,card.url);
  }
  text+='\n\n';
  if(index) text=addReportLink(text,entities,'◀️',reportLink(source,'list',index-1))+'  ';
  if(index+1<total) text=addReportLink(text,entities,'▶️',reportLink(source,'list',index+1))+'  ';
  if(view.notes) text=addReportLink(text,entities,'💶 '+notes,reportLink(source,'notes'));
  if(view.notes) text+='\n\n'+view.notes.split('\n').at(-1);
  return {text,entities};
}
async function reportHash(report:string) {
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(report));
  return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('').slice(0,12);
}
async function sendReport(id:number,report:string,source:string,language:string) {
  if(!report) { await reply(id,language==='fa'?'این گزارش منقضی شده است. داده‌های آپارتمان پس از هفت روز پاک می‌شوند.':language==='de'?'Dieser Bericht ist abgelaufen. Wohnungsdaten werden nach sieben Tagen gelöscht.':'This report has expired. Apartment data is removed after seven days.'); return; }
  const view=splitReport(report);
  if(!view.cards.length) return reply(id,report);
  for(let i=0;i<Math.ceil(view.cards.length/5);i++) {
    const page=reportPage(view,source,i,language);
    if(i) await new Promise(resolve=>setTimeout(resolve,1100));
    await reply(id,page.text,undefined,page.entities);
  }
}

const buttons = {inline_keyboard:[[{text:'⚙️ My settings',callback_data:'settings'},{text:'🔎 Run analysis',callback_data:'run'}],[{text:'📂 Saved report (free)',callback_data:'saved'},{text:'Help',callback_data:'help'}],[{text:'📖 Setup guide',callback_data:'guide:resume'}]]};
async function dispatch(job: string) {
  const repo = env('GITHUB_REPOSITORY');
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) throw new Error('Invalid repository');
  const r = await fetch('https://api.github.com/repos/'+repo+'/actions/workflows/analyse.yml/dispatches', {
    method:'POST',headers:{Authorization:'Bearer '+env('GITHUB_DISPATCH_TOKEN'),Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'},
    body:JSON.stringify({ref:'main',inputs:{job_id:job}}),signal:AbortSignal.timeout(10000)
  });
  if (!r.ok) throw new Error('Dispatch failed');
}

const PAYMENT_GUIDE='One report is paid separately; no credit bundle is required. A 30-day pass covers every scheduled weekly delivery within its active dates (including a fifth weekly date when applicable), with no automatic renewal. Extra manual reports are separate purchases. Reopening delivered reports is free while their data remains stored (seven days). A failed single report or failed delivery is refunded in Stars. A delivered report may have missing fields, few matches or no matches; market coverage is not guaranteed. /paysupport contacts the operator about payments. Telegram support does not handle this bot’s purchases. The invoice shows the binding Stars amount; the euro cost of obtaining Stars varies.';
function paymentExempt(user:any,admin:boolean) { return admin||user.pilot_free===true; }
async function paymentShop(id:number,user:any,control:any,admin:boolean) {
  if(paymentExempt(user,admin)) { await reply(id,'✅ Your current pilot/administrator access remains free. No payment is required.');return; }
  if(!control?.payments_enabled||!control?.payment_terms_text||!Number.isInteger(control?.report_price_stars)||!Number.isInteger(control?.weekly_price_stars)) { await reply(id,'Payments are not open yet. Planned prices: €0.99 per report and €3.96 for 30 days of weekly reports. Checkout will show a fixed Stars price; its euro equivalent varies. Current pilot users remain free.');return; }
  await reply(id,`⭐ Choose a purchase
One report: ${control.report_price_stars} Stars
30 days of weekly reports: ${control.weekly_price_stars} Stars

`+PAYMENT_GUIDE,
    {inline_keyboard:[[{text:'Read payment terms',callback_data:'pay:terms'}],...(user.payment_terms_version===1?[[{text:'Buy one report',callback_data:'pay:report'},{text:'Buy 30-day weekly pass',callback_data:'pay:weekly30'}]]:[])]});
}
async function paymentInvoice(id:number,user:any,control:any,product:string,admin:boolean) {
  if(paymentExempt(user,admin)) { await reply(id,'Your pilot/administrator access is free. Use /run.');return; }
  if(user.payment_terms_version!==1) { await reply(id,'Read /terms and accept the payment terms before buying.');return; }
  const order=await db('POST','rpc/bot_order_create',{p_user:id,p_product:product});
  if(order.error) { await reply(id,'Purchase not started: '+order.error+'. Use /paysupport if needed.');return; }
  await tg('sendInvoice',{chat_id:id,title:product==='report'?'One property screening report':'30 days of weekly property reports',
    description:product==='report'?'Report with your current settings, using available research. Missing data or no matches possible. Failed report/delivery refunded. Data stored for seven days.':'All scheduled weekly reports during 30 days, including a fifth weekly date if applicable. Manual runs extra. No auto-renewal. Limited search coverage; no guaranteed matches.',
    payload:'housing:'+order.order_id,provider_token:'',currency:'XTR',prices:[{label:product==='report'?'One report':'30-day weekly pass',amount:order.amount_stars}],start_parameter:'purchase'});
}
function paymentOrderId(payload:unknown) {
  const match=/^housing:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/.exec(String(payload));
  if(!match) throw new Error('Invalid payment payload');return match[1];
}

Deno.serve(async req => {
  let replyTo: number | undefined;
  if (req.method!=='POST') return new Response('Method not allowed',{status:405});
  if (req.headers.get('X-Telegram-Bot-Api-Secret-Token')!==env('TELEGRAM_WEBHOOK_SECRET')) return new Response('Forbidden',{status:403});
  if (Number(req.headers.get('content-length') || 0)>16000) return new Response('Too large',{status:413});
  try {
    const raw = await req.text();
    if (raw.length>16000) return new Response('Too large',{status:413});
    const update = JSON.parse(raw);
    // Checkout updates have no message; answer promptly before normal chat routing.
    if(update.pre_checkout_query) {
      const q=update.pre_checkout_query;
      try {
        const result=await db('POST','rpc/bot_order_checkout',{p_user:Number(q.from.id),p_id:paymentOrderId(q.invoice_payload),p_amount:q.total_amount,p_currency:q.currency,p_checkout:q.id},5000);
        await tg('answerPreCheckoutQuery',{pre_checkout_query_id:q.id,ok:result.ok===true,...(result.ok===true?{}:{error_message:'Purchase unavailable: '+result.error+'. Please request a new invoice or use /paysupport.'})});
      } catch { await tg('answerPreCheckoutQuery',{pre_checkout_query_id:q.id,ok:false,error_message:'Checkout unavailable. Please try later; no report was purchased.'}); }
      return new Response('ok');
    }
    const cb = update.callback_query;
    const message = update.message || cb?.message;
    const sender = message?.refunded_payment?{id:message.chat?.id,is_bot:false}:cb?.from || message?.from;
    if (!sender || sender.is_bot || message?.chat?.type!=='private') return new Response('ok');
    const id = Number(sender.id);
    if (!Number.isSafeInteger(id) || message.chat.id!==id) return new Response('Forbidden',{status:403});
    replyTo=id;
    if(message.refunded_payment) {
      await db('POST','rpc/bot_order_refunded',{p_user:id,p_charge:message.refunded_payment.telegram_payment_charge_id});
      return new Response('ok');
    }
    if(message.successful_payment) {
      const paid=message.successful_payment;
      const result=await db('POST','rpc/bot_order_paid',{p_user:id,p_id:paymentOrderId(paid.invoice_payload),p_amount:paid.total_amount,p_currency:paid.currency,p_charge:paid.telegram_payment_charge_id});
      if(!result.duplicate) {
        if(result.state==='refund_pending') await reply(id,'The purchase could not be fulfilled. A full Stars refund has been queued. Use /paysupport if you need help.');
        else if(result.product==='weekly30') await reply(id,'✅ Weekly pass purchased. Active from '+result.starts_at+' until '+result.ends_at+'. All weekly delivery dates in that interval are included. No automatic renewal; extra manual reports are separate.');
        else await reply(id,'✅ Payment received. Your report is queued and will arrive here. Failed analysis or delivery is refunded in Stars.');
      }
      if(result.job_id||result.state==='refund_pending') { try { await dispatch(result.job_id||''); } catch { /* Hourly worker recovers the durable order/job/refund. */ } }
      return new Response('ok');
    }
    if (cb) await tg('answerCallbackQuery',{callback_query_id:cb.id});
    const admin = Number(env('ADMIN_USER_ID'));
    let action=cb?String(cb.data):'';
    if(!cb) {
      const deep=/^\/start(?:@[A-Za-z0-9_]+)?\s+(prop|list|notes)_((?:j[0-9a-f-]{36}|s[0-9a-f]{12}))(?:_(\d+))?$/.exec(String(message.text||''));
      if(deep) action=deep[1]+':'+deep[2]+(deep[3]===undefined?'':':'+deep[3]);
    }
    let rows = await db('GET','bot_users?user_id=eq.'+id);
    if (!rows.length && id===admin) rows = await db('POST','bot_users',{user_id:id,approved:true});
    // Only the configured private administrator can bind the database quota exemption.
    let adminUnlimited=false;
    if (id===admin) {
      const control=(await db('GET','bot_control?id=eq.1'))[0];
      if (control&&Object.prototype.hasOwnProperty.call(control,'admin_user_id')) {
        if (Number(control.admin_user_id)!==admin) await db('PATCH','bot_control?id=eq.1',{admin_user_id:admin});
        adminUnlimited=true;
      }
    }
    // Decisions are private, admin-only, and bound to the latest pending request.
    if (action.startsWith('access:')) {
      if (id!==admin) { await reply(id,'Only the administrator can decide access requests.'); return new Response('ok'); }
      const match=/^access:(approve|decline):(\d+):([a-f0-9]{12})$/.exec(action);
      if (!match) throw new Error('Invalid access decision');
      const target=Number(match[2]);
      if (!Number.isSafeInteger(target)||target<=0||target===admin) throw new Error('Invalid user');
      const targets=await db('GET','bot_users?user_id=eq.'+target);
      const candidate=targets[0];
      if (!candidate||candidate.approved||candidate.settings?._access?.status!=='pending'||candidate.settings._access.nonce!==match[3]) {
        await reply(id,'This request has already been decided or replaced.'); return new Response('ok');
      }
      const approved=match[1]==='approve';
      const settings={...candidate.settings,_access:{...candidate.settings._access,status:approved?'approved':'declined'}};
      const changed=await db('PATCH','bot_users?user_id=eq.'+target+'&approved=eq.false&settings->_access->>nonce=eq.'+match[3]+'&settings->_access->>status=eq.pending',
        {approved,settings,...(approved?{plan:'free'}:{})});
      if (!changed.length) { await reply(id,'This request has already been decided or replaced.'); return new Response('ok'); }
      await reply(id,(approved?'✅ Approved':'Declined')+' access for Telegram ID '+target+(approved?'. Free plan: one report per week.':'.'));
      try { await reply(target,approved?'✅ Your access is approved. Your free plan allows one report per week. Send /start and accept the notice to continue.':'Your access request was declined. You can request again 24 hours after your previous request.'); }
      catch { await reply(id,'The decision was saved, but notification failed. The user can send /start to check access.'); }
      return new Response('ok');
    }
    if (!rows.length || !rows[0].approved) {
      if (action==='request_access') {
        if (!rows.length) rows=await db('POST','bot_users',{user_id:id,approved:false});
        const candidate=rows[0]; const previous=candidate.settings?._access;
        if (previous?.status==='pending') {
          await reply(id,'Your request is waiting for approval. The bot will notify you here.'); return new Response('ok');
        }
        if (previous?.at&&Date.now()-previous.at<24*60*60*1000) {
          await reply(id,'You can send another request 24 hours after your previous request.'); return new Response('ok');
        }
        const nonce=crypto.randomUUID().replaceAll('-','').slice(0,12);
        const settings={...candidate.settings,_access:{status:'pending',nonce,at:Date.now()}};
        // Conditional write also prevents duplicate webhook deliveries from notifying twice.
        const condition=previous?.nonce?'&settings->_access->>nonce=eq.'+previous.nonce:'&settings->_access=is.null';
        const changed=await db('PATCH','bot_users?user_id=eq.'+id+'&approved=eq.false'+condition,{settings});
        if (!changed.length) { await reply(id,'Your request is already recorded. Send /start to check access.'); return new Response('ok'); }
        const name=String(sender.first_name||'Telegram user').replace(/[\r\n]/g,' ').slice(0,80);
        try {
          await reply(admin,'📩 Access request\nName: '+name+'\nTelegram ID: '+id+'\nApproval grants the free plan: one report per week.',
            {inline_keyboard:[[{text:'✅ Approve',callback_data:'access:approve:'+id+':'+nonce},{text:'Decline',callback_data:'access:decline:'+id+':'+nonce}]]});
        } catch {
          const retrySettings={...candidate.settings}; delete retrySettings._access;
          await db('PATCH','bot_users?user_id=eq.'+id+'&approved=eq.false&settings->_access->>nonce=eq.'+nonce+'&settings->_access->>status=eq.pending',{settings:retrySettings});
          await reply(id,'Could not send your request. Please tap Request access again later.');
          return new Response('ok');
        }
        await reply(id,'✅ Access request sent. You will receive the decision here; you do not need to contact anyone privately.');
      } else {
        await reply(id,'This bot currently requires approval. Tap Request access to send your Telegram name and ID privately to the administrator. The decision will arrive here.',
          {inline_keyboard:[[{text:'Request access',callback_data:'request_access'}]]});
      }
      return new Response('ok');
    }
    const user = rows[0];
    user.admin_unlimited=adminUnlimited;
    const billingControl=(await db('GET','bot_control?id=eq.1'))[0];
    user.pilot_locked=Boolean(billingControl?.pilot_locked);
    user.payments_active=Boolean(billingControl?.payments_enabled)&&!paymentExempt(user,adminUnlimited);
    const text = String(cb ? '/'+cb.data : message.text || '').slice(0,2500).trim();
    const [rawcmd, ...parts] = text.split(/\s+/);
    const cmd = rawcmd.split('@')[0].toLowerCase();
    const rest = parts.join(' ');
    if(cmd==='/terms'||action==='pay:terms') {
      await reply(id,(billingControl?.payment_terms_text||'Payments are not yet open. The operator’s payment terms will be displayed here before checkout.')+'\n\n'+PAYMENT_GUIDE,
        billingControl?.payments_enabled&&billingControl?.payment_terms_text?{inline_keyboard:[[{text:'I agree to the payment terms',callback_data:'pay:accept'}]]}:undefined);
      return new Response('ok');
    }
    if(action==='pay:accept') {
      if(!billingControl?.payments_enabled||!billingControl?.payment_terms_text) { await reply(id,'Payments are not open yet.');return new Response('ok'); }
      await db('PATCH','bot_users?user_id=eq.'+id,{payment_terms_version:1});user.payment_terms_version=1;
      await paymentShop(id,user,billingControl,adminUnlimited);return new Response('ok');
    }
    if(cmd==='/buy'||action==='buy'||action==='pay:report'||action==='pay:weekly30') {
      if(action.startsWith('pay:')&&user.settings._guide_version!==1) { await reply(id,'Complete /guide first. No payment started.');return new Response('ok'); }
      if(action==='pay:report'||action==='pay:weekly30') await paymentInvoice(id,user,billingControl,action.slice(4),adminUnlimited);
      else await paymentShop(id,user,billingControl,adminUnlimited);
      return new Response('ok');
    }
    if(id===admin&&cmd==='/refund') {
      if(!/^[0-9a-f-]{36}$/.test(rest)) { await reply(id,'Use /refund ORDER_UUID (from /payments).');return new Response('ok'); }
      const orders=await db('GET','bot_orders?id=eq.'+rest);
      if(!orders[0]||!['paid','delivered','refund_pending'].includes(orders[0].state)) { await reply(id,'No refundable purchase found.');return new Response('ok'); }
      const active=orders[0].job_id?await db('GET','bot_jobs?id=eq.'+orders[0].job_id+'&status=in.(queued,running)'):[];
      if(active.length) { await reply(id,'Wait until the running report finishes before refunding this order.');return new Response('ok'); }
      await db('PATCH','bot_orders?id=eq.'+rest+'&state=in.(paid,delivered,refund_pending)',{state:'refund_pending'});
      await reply(id,'Full Stars refund queued. Weekly access from that pass will end.');
      try { await dispatch(''); } catch { /* Durable refund remains queued. */ }
      return new Response('ok');
    }
    if(id===admin&&cmd==='/payments') {
      if(!Object.hasOwn(billingControl||{},'payments_enabled')) { await reply(id,'Apply migration 007 before payment setup.');return new Response('ok'); }
      const orders=await db('GET','bot_orders?order=created_at.desc&limit=10&select=id,product,amount_stars,state');
      await reply(id,'Payments: '+(billingControl.payments_enabled?'enabled':'off')+'\nConfigured Stars: '+billingControl.report_price_stars+' per report / '+billingControl.weekly_price_stars+' per 30 days\nCurrent pilot users are exempt.\n'+orders.map((o:any)=>`${o.id} · ${o.product} · ${o.amount_stars} Stars · ${o.state}`).join('\n'));
      return new Response('ok');
    }
    if(user.pilot_locked && (['/set','/location','/areas','/exclude','/schedule','/weekly'].includes(cmd) || /^(menu:|edit:|lang:|day:|weekly:)/.test(action) || (!cb&&!text.startsWith('/')&&user.settings._edit))) {
      await reply(id,'🔒 Pilot settings and weekly schedule are fixed for all users. Reports are scheduled Monday at 09:00 Europe/Berlin. Use /settings to review the preset or /support for help.');
      return new Response('ok');
    }
    const clearEdit=async()=>{
      const clean={...user.settings}; delete clean._edit;
      await db('PATCH','bot_users?user_id=eq.'+id,{settings:clean}); user.settings=clean;
    };
    if(user.accepted_at&&(cmd==='/guide'||action.startsWith('guide:'))) {
      const seen=Number(user.settings._guide_seen??-1);
      if(action==='guide:complete' && seen>=6) {
        await clearEdit();
        await db('PATCH','bot_users?user_id=eq.'+id,{settings:{...user.settings,_guide_version:1}});
        await reply(id,user.settings.language==='fa'?'✅ راهنما تکمیل شد. تنظیمات را بررسی کنید؛ برای شروع تحلیل /run را بفرستید.':user.settings.language==='de'?'✅ Anleitung abgeschlossen. Einstellungen prüfen; /run startet eine Analyse.':'✅ Guide completed. Review your settings; send /run when ready to start an analysis.',buttons);
        return new Response('ok');
      }
      const requested=cmd==='/guide'?0:action==='guide:resume'||action==='guide:complete'?(user.settings._guide_step??0):Number(action.slice(6));
      const chosen=Math.max(0,Math.min(6,seen+1,Number.isFinite(requested)?requested:0));
      const guide=setupGuide(chosen,user.settings.language,user);
      await clearEdit();
      await db('PATCH','bot_users?user_id=eq.'+id,{settings:{...user.settings,_guide_step:chosen,_guide_seen:Math.max(seen,chosen)}});
      await reply(id,guide.text,guide.keyboard);
      return new Response('ok');
    }
    if (user.accepted_at && /^(prop|list|notes):/.test(action)) {
      const match=/^(prop|list|notes):((?:j[0-9a-f-]{36}|s[0-9a-f]{12}))(?::(\d+))?$/.exec(action);
      if(!match) throw new Error('Invalid report navigation');
      const [_,kind,source,rawIndex]=match;
      let report='';
      if(source.startsWith('j')) {
        const stored=await db('GET','bot_jobs?id=eq.'+source.slice(1)+'&user_id=eq.'+id+'&status=eq.complete&select=report');
        report=stored[0]?.report||'';
      } else {
        const stored=await db('POST','rpc/bot_saved_report',{p_user:id});
        if(stored?.report && 's'+await reportHash(stored.report)===source) report=stored.report;
      }
      if(!report) { await reply(id,'This report is no longer available. Use /last or /saved.'); return new Response('ok'); }
      const view=splitReport(report);const index=Number(rawIndex);
      let display:string;let displayEntities:any[]=[];
      if(kind==='list') { const page=reportPage(view,source,index,user.settings.language);display=page.text;displayEntities=page.entities; }
      else {
        if(kind==='prop'&&(!Number.isSafeInteger(index)||index<0||index>=view.cards.length)) throw new Error('Invalid apartment');
        display=kind==='notes'?view.notes:view.cards[index].detail;
        if(kind==='prop'&&view.notes) display+='\n\n'+view.notes.split('\n').at(-1);
        display+='\n\n';
        display=addReportLink(display,displayEntities,reportLabels(user.settings.language)[4],reportLink(source,'list',0));
      }
      if(message.text===display) return new Response('ok');
      if(cb&&display.length<=3800&&message.message_id) await tg('editMessageText',{chat_id:id,message_id:message.message_id,text:display,entities:displayEntities,reply_markup:{inline_keyboard:[]},link_preview_options:{is_disabled:true}});
      else await reply(id,display,undefined,displayEntities);
      return new Response('ok');
    }
    if (user.accepted_at && (cmd==='/cancel'||action==='cancel')) {
      await clearEdit(); await reply(id,'Edit cancelled. Your settings are unchanged.',settingsButtons); return new Response('ok');
    }
    if (user.accepted_at && action.startsWith('menu:')) {
      await clearEdit(); const group=action.slice(5);
      let keyboard:any;
      if (group==='exclude') {
        keyboard={inline_keyboard:[...['Erbpacht','Zwangsversteigerung'].map(x=>[button((user.settings.exclude.includes(x)?'☑️ ':'⬜ ')+(x==='Erbpacht'?'Exclude leasehold':'Exclude foreclosure auctions'),'toggle:'+x)]),[button('← My settings','settings')]]};
        await reply(id,'🚫 Exclusions\nTap an item to turn its exclusion on or off.',keyboard);
      } else if (GROUPS[group]) {
        const rows=GROUPS[group].map(f=>[button(LABELS[f],'edit:'+f)]);
        if (group==='schedule') {
          rows.unshift([button('Change weekday','days')]);
          rows.push([button(user.weekly?'Turn weekly reports off':'Turn weekly reports on',user.weekly?'weekly:off':'weekly:on')]);
        }
        rows.push([button('← My settings','settings')]);
        await reply(id,'Choose the setting to change:',{inline_keyboard:rows});
      } else await reply(id,'Open /settings to choose a setting.',settingsButtons);
      return new Response('ok');
    }
    if (user.accepted_at && action==='days') {
      await clearEdit(); await reply(id,'Choose your delivery day:',{inline_keyboard:[...DAYS.map((d,i)=>[button(d,'day:'+i)]),[button('← My settings','settings')]]}); return new Response('ok');
    }
    if (user.accepted_at && /^(day:|weekly:|toggle:)/.test(action)) {
      await clearEdit();
      if (action.startsWith('day:')) {
        const day=Number(action.slice(4)); if (!Number.isInteger(day)||day<0||day>6) throw new Error('Invalid day');
        await db('PATCH','bot_users?user_id=eq.'+id,{schedule_day:day});
        await reply(id,'✅ Delivery day saved: '+DAYS[day],settingsButtons);
      } else if (action.startsWith('weekly:')) {
        if (!['weekly:on','weekly:off'].includes(action)) throw new Error('Invalid choice');
        await db('PATCH','bot_users?user_id=eq.'+id,{weekly:action==='weekly:on'});
        await reply(id,'✅ Weekly reports '+(action==='weekly:on'?'on':'off')+'. Scheduled reports count toward your weekly allowance.',settingsButtons);
      } else {
        const item=action.slice(7); if (!['Erbpacht','Zwangsversteigerung'].includes(item)) throw new Error('Invalid exclusion');
        const list=user.settings.exclude.includes(item)?user.settings.exclude.filter((x:string)=>x!==item):[...user.settings.exclude,item];
        await db('PATCH','bot_users?user_id=eq.'+id,{settings:{...user.settings,exclude:list}});
        await reply(id,'✅ Exclusions updated. Open Exclusions again to see current choices.',settingsButtons);
      }
      return new Response('ok');
    }
    if (user.accepted_at && action.startsWith('edit:')) {
      const field=action.slice(5); if (!LABELS[field]) throw new Error('Invalid edit field');
      if (field==='language') {
        await clearEdit(); await reply(id,'Choose your report language:',{inline_keyboard:[[button('English','lang:en'),button('Deutsch','lang:de'),button('فارسی','lang:fa')],[button('Cancel','cancel')]]});
      } else {
        await db('PATCH','bot_users?user_id=eq.'+id,{settings:{...user.settings,_edit:{field,at:Date.now()}}});
        await reply(id,editPrompt(field),{inline_keyboard:[[button('Cancel','cancel')]]});
      }
      return new Response('ok');
    }
    if (user.accepted_at && action.startsWith('lang:')) {
      const language=parseEdit('language',action.slice(5)); await clearEdit();
      await db('PATCH','bot_users?user_id=eq.'+id,{settings:{...user.settings,language}});
      await reply(id,'✅ Report language saved: '+(language==='fa'?'فارسی':language==='en'?'English':'German'),settingsButtons); return new Response('ok');
    }
    if (user.accepted_at && !cb && !text.startsWith('/') && user.settings._edit) {
      const pending=user.settings._edit;
      if (Date.now()-pending.at>15*60*1000 || !LABELS[pending.field]) {
        await clearEdit(); await reply(id,'This edit expired. Open /settings and choose the field again.',settingsButtons);
      } else {
        try {
          const value=parseEdit(pending.field,text);
          const clean={...user.settings}; delete clean._edit;
          if (['schedule_time','timezone'].includes(pending.field)) await db('PATCH','bot_users?user_id=eq.'+id,{settings:clean,[pending.field]:value});
          else {
            const settings={...clean,[pending.field]:value};
            if (pending.field==='location') { settings.areas=[]; settings.country='Germany'; }
            await db('PATCH','bot_users?user_id=eq.'+id,{settings});
          }
          await reply(id,'✅ '+LABELS[pending.field]+' saved: '+(value===null?'No filter':Array.isArray(value)?value.join(', ')||'None':value),settingsButtons);
        } catch(e) {
          await reply(id,e instanceof Error?e.message:'Could not save. Try again.',{inline_keyboard:[[button('Cancel','cancel')]]});
        }
      }
      return new Response('ok');
    }
    // A command exits a pending edit; plain text only changes the explicitly selected field.
    if (user.settings._edit && (cb || text.startsWith('/'))) await clearEdit();
    // /run uses an atomic unique request key in SQL. Other commands are idempotent,
    // except /support which gets a dedicated unique update record.
    if (cmd==='/start' || cmd==='/disclaimer') {
      await reply(id,NOTICE,{inline_keyboard:[[{text:'I understand — continue',callback_data:'accept'}]]});
    } else if (cmd==='/accept') {
      await db('PATCH','bot_users?user_id=eq.'+id,{accepted_at:new Date().toISOString()});
      const guide=setupGuide(0,user.settings.language,user);
      await db('PATCH','bot_users?user_id=eq.'+id,{settings:{...user.settings,_guide_step:0,_guide_seen:Math.max(0,Number(user.settings._guide_seen??-1))}});
      await reply(id,guide.text,guide.keyboard);
    } else if (cmd==='/help') {
      await reply(id,(user.settings.language==='fa'?HELP_FA:HELP).replace(user.payments_active?'Free: 1 report/week. Paid: up to 7. Scheduled reports count too. Reset Monday 00:00 Europe/Berlin. Manual membership during pilot.':'__unused__',user.payments_active?'Paid reports are purchased individually; the 30-day pass covers weekly deliveries.':'')+(user.payments_active?'\n\n'+PAYMENT_GUIDE:'')+'\n\n'+(user.settings.language==='fa'?CALCULATIONS_FA:user.settings.language==='de'?CALCULATIONS_DE:CALCULATIONS_EN),buttons);
    } else if (cmd==='/support'||cmd==='/paysupport') {
      if (!rest) await reply(id,'Send /support followed by your question. It is forwarded to the administrator; no AI charge. Response is manual.');
      else {
        const existing = await db('GET','bot_updates?update_id=eq.'+Number(update.update_id));
        if (!existing.length) {
          await reply(admin,'📩 Support from Telegram ID '+id+'\n'+rest);
          await db('POST','bot_updates',{update_id:Number(update.update_id)});
        }
        await reply(id,'Your question was sent to the administrator. Response is manual, not immediate.');
      }
    } else if (id===admin && cmd==='/channel') {
      if (!['on','off'].includes(rest)) throw new Error('Use /channel on|off');
      await db('PATCH','bot_control?id=eq.1',{channel_enabled:rest==='on'});
      await reply(id,'Channel posting '+rest+'. Only your reports are shared; configure CHANNEL_ID in GitHub secrets and grant the bot posting permission.');
    } else if (id===admin && cmd==='/cost') {
      const month=new Date().toISOString().slice(0,7)+'-01T00:00:00Z';
      const jobs=await db('GET','bot_jobs?created_at=gte.'+month+'&select=charged_usd,reserved_usd,status');
      const total=jobs.reduce((s:number,j:any)=>s+Number(j.charged_usd??j.reserved_usd),0);
      const control=(await db('GET','bot_control?id=eq.1'))[0];
      await reply(id,`Monthly estimates/reservations: $${total.toFixed(2)} / $${control.monthly_budget_usd}\nUnknown usage: ${jobs.filter((j:any)=>j.status==='uncertain').length}. Reconcile with OpenAI billing; taxes/FX/hosting separate.`);
    } else if (id===admin && ['/approve','/plan','/reply'].includes(cmd)) {
      const target = Number(parts[0]);
      if (!Number.isSafeInteger(target) || target<=0) throw new Error('Invalid user ID');
      if (cmd==='/approve') {
        const known = await db('GET','bot_users?user_id=eq.'+target);
        await db(known.length?'PATCH':'POST',known.length?'bot_users?user_id=eq.'+target:'bot_users',{user_id:target,approved:true});
        await reply(id,'User approved. They must /start and accept the notice.');
      } else if (cmd==='/plan') {
        if (!['free','paid'].includes(parts[1])) throw new Error('Use /plan ID free|paid');
        const result = await db('PATCH','bot_users?user_id=eq.'+target,{plan:parts[1]});
        await reply(id,result.length?'Membership updated.':'User not found.');
      } else {
        const known = await db('GET','bot_users?user_id=eq.'+target+'&approved=eq.true');
        if (!known.length || !parts.slice(1).join(' ')) throw new Error('Use /reply APPROVED_USER_ID MESSAGE');
        await reply(target,'Support reply:\n'+parts.slice(1).join(' '));
        await reply(id,'Reply sent.');
      }
    } else if (!user.accepted_at) {
      await reply(id,'Please /start and accept the notice first.');
    } else if (cmd==='/settings') {
      await reply(id,settingsSummary(user),user.pilot_locked?{inline_keyboard:[[button('📖 Guide','guide:resume'),button('❓ Help','help')],[button('📂 Saved report','saved'),button('🔎 Run analysis','run')]]}:settingsButtons);
    } else if (cmd==='/set' || cmd==='/location' || cmd==='/areas' || cmd==='/exclude') {
      const settings = {...user.settings};
      if (cmd==='/location') {
        if (!rest || rest.length>100) throw new Error('Use /location CITY, Germany only');
        settings.location=rest; settings.country='Germany'; settings.areas=[];
      } else if (cmd==='/areas' || cmd==='/exclude') {
        if (!rest || rest.length>500) throw new Error('Provide a comma-separated list, or none');
        settings[cmd.slice(1)] = rest==='none'?[]:rest.split(',').map((x:string)=>x.trim()).filter(Boolean).slice(0,15);
      } else {
        const field = parts[0], value = parts[1];
        if (parts.length!==2) throw new Error('Use /set FIELD VALUE');
        if (field==='language') {
          if (!['en','de','fa'].includes(value)) throw new Error('Language must be en, de or fa');
          settings[field]=value;
        } else if (OPTIONAL.has(field) && value==='none') settings[field]=null;
        else {
          const bounds=MAX[field], n=Number(value);
          if (!bounds || !Number.isFinite(n) || n<bounds[0] || n>bounds[1] || (field==='fixed_rate_years' && !Number.isInteger(n))) throw new Error('Unknown field or invalid value; see /help');
          settings[field]=n;
        }
      }
      await db('PATCH','bot_users?user_id=eq.'+id,{settings});
      await reply(id,'Settings saved. Germany only during pilot.');
    } else if (cmd==='/schedule') {
      const day=['mon','tue','wed','thu','fri','sat','sun'].indexOf(parts[0]?.toLowerCase());
      if (parts.length!==3 || day<0 || !/^([01]\d|2[0-3]):[0-5]\d$/.test(parts[1])) throw new Error('Use /schedule mon 08:00 Europe/Berlin');
      try { new Intl.DateTimeFormat('en',{timeZone:parts[2]}).format(); } catch { throw new Error('Invalid timezone'); }
      await db('PATCH','bot_users?user_id=eq.'+id,{schedule_day:day,schedule_time:parts[1],timezone:parts[2]});
      await reply(id,'Schedule saved. Delivery is checked hourly and may be delayed. Use /weekly on to enable.');
    } else if (cmd==='/weekly') {
      if (!['on','off'].includes(rest)) throw new Error('Use /weekly on|off');
      await db('PATCH','bot_users?user_id=eq.'+id,{weekly:rest==='on'});
      await reply(id,'Weekly reports '+rest+(adminUnlimited?'. Your administrator account has no weekly report limit.':'. They count toward your quota.'));
    } else if (cmd==='/quota') {
      // SQL uses server-side Berlin week reset. Fetch latest jobs, calculate with Berlin date.
      const local = new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
      const d=new Date(local+'T12:00:00Z'); d.setUTCDate(d.getUTCDate()-((d.getUTCDay()+6)%7));
      const week=d.toISOString().slice(0,10);
      const jobs=await db('GET','bot_jobs?user_id=eq.'+id+'&week_start=eq.'+week+'&select=status,charged_usd,usage');
      const used=jobs.filter((j:any)=>j.usage?.shared_hit!==true&&(j.status!=='failed'||Number(j.charged_usd)>0)).length;
      if(user.payments_active) { await paymentShop(id,user,billingControl,adminUnlimited);return new Response('ok'); }
      await reply(id,adminUnlimited?`Administrator: no weekly report limit.\nReports this week: ${used}.\nMonthly spending cap and one active analysis at a time still apply.`:`Plan: ${user.plan}\nUsed: ${used} / ${user.plan==='paid'?7:1} this week. Reset Monday 00:00 Europe/Berlin.`);
    } else if (cmd==='/last') {
      const jobs=await db('GET','bot_jobs?user_id=eq.'+id+'&status=eq.complete&order=finished_at.desc&limit=1&select=id,report');
      if(jobs.length) await sendReport(id,jobs[0].report,'j'+jobs[0].id,user.settings.language);
      else await reply(id,'No completed report yet.');
    } else if (cmd==='/run'||cmd==='/saved'||cmd==='/refresh') {
      if(cmd!=='/saved' && user.settings._guide_version!==1) {
        const step=Math.max(0,Math.min(6,Number(user.settings._guide_step??0)));
        const guide=setupGuide(step,user.settings.language,user);
        await db('PATCH','bot_users?user_id=eq.'+id,{settings:{...user.settings,_guide_seen:Math.max(Number(user.settings._guide_seen??-1),step)}});
        await reply(id,guide.text,guide.keyboard); return new Response('ok');
      }
      const refresh=cmd==='/refresh';
      if (refresh && id!==admin) { await reply(id,'Only the administrator can start additional paid research.'); return new Response('ok'); }
      const control=(await db('GET','bot_control?id=eq.1'))[0];
      if (control?.shared_reports_enabled && !refresh) {
        const saved=await db('POST','rpc/bot_saved_report',{p_user:id});
        if (saved?.report) {
          await reply(id,'📂 Saved report for your current settings. No quota used and no new AI research.');
          await sendReport(id,saved.report,'s'+await reportHash(saved.report),user.settings.language); return new Response('ok');
        }
      }
      if (cmd==='/saved') {
        await reply(id,'No current shared report matches your exact settings. /last shows your previous report for free; /run can create a new personalised report within your allowance.');
        return new Response('ok');
      }
      if (!control?.research_v2) {
        await reply(id,'Analysis paused until the cost-saving upgrade is activated. No paid run started. Use /last for your saved report.');
        return new Response('ok');
      }
      const result=await db('POST','rpc/bot_enqueue',{p_user:id,p_key:(refresh?'refresh:':'telegram:')+update.update_id});
      if (result.error==='payment_required') await paymentShop(id,user,control,adminUnlimited);
      else if (result.error) await reply(id,'Analysis not started: '+result.error+'. Use /support if you need help.');
      else if (result.duplicate) await reply(id,'This request is already recorded. Use /last for the latest report.');
      else {
        try { await dispatch(result.job_id); await reply(id,refresh?'Additional paid research queued within the monthly cap. Saved apartments will be retained.':'Analysis queued. Results will arrive here; GitHub may take a few minutes.'); }
        catch { await reply(id,'Request saved but immediate dispatch failed. The scheduled worker can recover it.'); await reply(admin,'⚠️ Dispatch failed. Job '+result.job_id); }
      }
    } else await reply(id,'Use /help for commands.',buttons);
    return new Response('ok');
  } catch {
    // No request payloads, secrets or financial settings in function logs.
    if (replyTo) {
      try {
        await reply(replyTo,'Could not process the request. Check syntax with /help, or /support your question. If already queued, do not repeatedly press Run.');
        return new Response('ok');
      } catch { /* Telegram retries only if even the error reply cannot be delivered. */ }
    }
    return new Response('Request could not be processed. Please check command syntax or contact operator.',{status:500});
  }
});
