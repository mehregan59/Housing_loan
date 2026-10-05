# Housing Loan Bot

Invite-only Telegram pilot for screening German buy-to-let apartments. Users choose a German city, search radius, financial limits, language and a weekly schedule. Other countries can be added later through country-specific taxes, financing and rental rules; changing the country is not enabled in this release.

**Status:** the legacy pilot is deployed. The shared-research upgrade is prepared and offline-tested, but stays disabled until migration 002 and explicit activation. No API call is made by the offline test workflow.

## Services

| Service | Role |
| --- | --- |
| Supabase | Private settings, jobs, quotas, cost ledger and Telegram webhook |
| GitHub Actions | Longer OpenAI analysis and scheduled report processing |
| OpenAI Responses API | Shared, structured web research; no calculation/report-writing call in v2 |
| Telegram | Buttons, commands, reports and support |

No always-running laptop is required. The old pilot used `gpt-6-astra`. The worker now blocks paid research if v2 is inactive, rather than falling back. The v2 extractor defaults to `gpt-6.1-sol` (`RESEARCH_MODEL`), supporting web search and structured outputs. Python performs calculations and writes reports. There is no automatic paid fallback to a more expensive model. Model/pricing configuration must be reviewed before changing it. The pilot has a separate $8 OpenAI project hard cap and a database budget of $8, chosen as a conservative allowance under the operator's €10 goal. Currency conversion, taxes and hosting are separate. $1/job is a **budget reservation, not a guaranteed maximum bill**: search-input token costs cannot be known precisely before the response completes. The OpenAI hard limit is the billing backstop and can slightly overshoot during propagation.

## User commands

- `/start`: information notice and explicit acceptance.
- `/help`: command examples, allowances and failure guidance.
- `/settings`: readable summary with buttons for individual settings. Tap a field, send a new value, and receive confirmation. `/cancel` exits; unanswered edits expire after 15 minutes. Language, day, exclusions and weekly on/off use selection buttons. No AI call is made for editing settings.
- `/set FIELD VALUE`: optional command shortcut for experienced users.
- `/location CITY`, `/areas CITY, CITY`: German search locations.
- `/exclude Erbpacht, Zwangsversteigerung`; `none` clears exclusions.
- `/schedule mon 08:00 Europe/Berlin`: editable weekday/time/timezone.
- `/weekly on|off`: enable automatic delivery (initially off).
- `/run`: analyse the latest shared data, also available as a button. It does not force a paid search in v2. Unchanged settings/data return the previous report. `/last` is the no-quota shortcut for retrieving a saved report.
- `/quota`: remaining weekly allowance; `/last`: latest saved report without a new API call.
- `/disclaimer`: estimates and data-use notice.
- `/support QUESTION`: forward question and Telegram ID to administrator; manual response, no AI cost.

Free membership permits one analysis/week, paid seven. The configured administrator has no weekly report quota after migration 003 and the next private bot interaction; the monthly spending cap, approval, uncertainty pause and one-active-job protection still apply. Scheduled reports count too. Reset Monday 00:00 Europe/Berlin. The pilot initially approves only the configured administrator, without committing their ID. Admin commands: `/approve ID`, `/plan ID free|paid`, `/reply ID MESSAGE`, `/cost`, `/channel on|off`. Optional channel/group posting shares only the admin's reports and requires a GitHub `CHANNEL_ID` secret and bot posting permissions. Payments are not collected automatically during this pilot.

Schedules are checked hourly at minute 17 UTC. Delivery can be up to an hour later plus GitHub queue delay; due slots can catch up within 24 hours. Local timezones use DST rules. GitHub scheduled workflows in public repositories can be disabled after 60 days without repository activity; watch the Actions page. Database health checks do not remove that GitHub limitation.

## Analysis and uncertainty

V2 aims to collect 20 distinct apartments with verified price and size per shared German location/radius pool, without investor financial limits. Portals and local agents are searched; individual pages must have a retrieved source URL and a recorded page-open action. This is a target, never a guarantee. All retained candidates within known user limits are shown, with missing criteria explicitly marked unchecked, plus up to three clearly labelled flexibility options when fewer than five strict matches exist. Reports may span several Telegram messages. No synthetic listings fill gaps.

Data is cached for seven days, refreshing saved URLs first when expired. Financing is shared by fixed-rate period and requires two independent, dated nominal-rate sources no more than 14 days old. Effective APR is not substituted in monthly-interest arithmetic. Empty research results are also cached to prevent repeated paid searches. The cache contains public research only, never private investor settings. Locations within 5 km can reuse a pool only when sourced municipality coordinates prove that its radius covers the request. Approximate town-center distances are disclosed. Additional areas rank preferred towns within the radius; they do not expand coverage.

Required loan = price × (1 + state transfer tax + estimated 2% notary/registry + stated buyer commission) − equity, never silently capped. Missing commission/tax leaves financing unknown and prevents confirmed matches. Monthly initial payment = loan × (nominal interest + initial repayment) / 1200. Gross yield = monthly cold rent × 1200 / price. Monthly result subtracts the mortgage, owner-only operating building fees excluding reserve contributions, and €1/m² maintenance. This is initial annuity screening, not full repayment within the fixed-rate period.

Actual and estimated rent/owner costs have source links. Estimates require a cited relevant basis; area alone does not justify building fees. Missing costs without reliable comparable evidence stay unknown. Major repairs/assessments are never invented. Recommendations enforce hard limits; flexibility options may differ by at most 10% on price, size, radius, loan, price/m² or yield, or €50/month on the cashflow target, with at most two differences. Exclusions and Germany are never relaxed. A higher loan requirement is explicitly labelled not financeable under the current cap; settings are never changed.

The fixed screening rubric starts at 2 points, adds up to 4 for gross yield (yield/2), 2 for nonnegative monthly results, and 1 for nonnegative stressed results; it subtracts 1 for energy E–H and 1 for unknown/estimated owner costs, then clamps to 0–10. New homes and preferred towns rank first, followed by this score and monthly result. Scores are subjective screens, not predictions. Source/shape checks cannot prove extracted amounts, stated availability or municipal coordinates are correct. Compare initial live results with listings before inviting a larger audience.

Public-facing notice: estimates only; general information, not financial advice or a financing commitment. Users must verify before deciding. The notice does not eliminate statutory operator obligations or liability. Before a public commercial launch, provide appropriate operator contact/imprint, privacy information and service terms reviewed for the actual service. No public paid launch is implemented here.

## Cost and recovery

Quota and budget reservations are atomic in PostgreSQL. Only one active job per user is permitted. Worker claims are atomic and check approval, acceptance, activation and global spending again. Click/webhook duplicates reuse one request record. Output tokens, built-in tool calls, timeout and automatic SDK retries are bounded; retries are disabled. V2 makes at most two research calls on an empty cache (four rate-tool calls and 24 listing-tool calls; output limits 4,000/14,000 tokens). It sends no investor finances or seen-URL histories to OpenAI. A complete cache hit costs $0 in OpenAI API usage; hosting remains separate. Costs include token usage, conservatively counted tool actions, legacy container sessions if applicable, and a 10% estimate buffer. Fresh-research cost is not guaranteed in advance. They are not official invoices.

V2 queues cached work with zero reservation and acquires a locked $1 research reservation before paid calls. Exhausted monthly search budgets block fresh research, while fresh cached reports can still run. Approval remains required. Newly calculated personalised reports count toward weekly quotas even if their research data is cached; retrieving an existing exact-setting report does not. Unknown usage or an interrupted running job pauses new analyses pending admin reconciliation. Failed jobs with known positive usage still count toward quota. Report delivery failure keeps the completed report for `/last`, without rerunning the paid analysis. Failed dispatch leaves a queued job for the next scheduled sweep.

Admin reconciliation: inspect OpenAI billing for the job time; record verified `charged_usd` and change an `uncertain` job to `failed` in Supabase. Never erase an uncertain reservation or retry blindly. Costs can be incurred even when no report is delivered.

Daily health checks verify database access and overdue queued jobs, update one bounded health record and alert the admin. They do not call OpenAI and **do not guarantee** that Supabase Free will avoid pausing. No automatic restore is implemented. Support forwarding is best effort; retries after uncertain Telegram delivery can duplicate a support notification.

## Tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

GitHub's offline workflow also checks TypeScript and runs the migration plus quota/budget tests on disposable PostgreSQL. It does not use production secrets or make paid requests. See [SETUP.md](SETUP.md) for staged deployment instructions.

License: [LICENSE](LICENSE).

## Invite users and control their allowance

Share the bot link. Unapproved users tap **Request access**; the button explains that their Telegram name and ID are sent privately to the administrator. The administrator receives **Approve / Decline** buttons in their private bot chat, and the bot delivers the decision to the applicant. The administrator's username/ID is never included in applicant messages, and applicants need not contact the administrator directly. Approval starts the free plan (one report/week), then the user sends `/start` and accepts the notice. `/approve ID` remains an administrator shortcut.

Pending requests cannot notify twice. Declined requests have a 24-hour cooldown measured from the request time. Each decision is bound to a request nonce and uses a conditional database update; stale buttons cannot reverse a completed decision or decide a replacement request. A saved decision is retained if the applicant's notification fails. Request state lives in internal settings metadata, excluded from OpenAI inputs and settings summaries. No new database migration or paid API call is required.

Only an administrator can send `/plan ID paid` to allow seven reports/week, or `/plan ID free` to return to one. Changing settings and `/last` cost no OpenAI tokens. New personalised reports count toward the weekly allowance; retrieving an existing exact-setting report does not.

## Shared-research upgrade

See the staged upgrade steps at the end of [SETUP.md](SETUP.md). Migration 002 preserves existing settings, reports and permissions and leaves `research_v2=false`. Do not rerun migration 001. No paid test is performed by applying the migration.

## Administrator weekly quota exemption

Apply `supabase/migrations/003_admin_quota.sql` once after 002, and deploy the latest webhook file. The next private administrator interaction binds `bot_control.admin_user_id` from the existing `ADMIN_USER_ID` secret; no identifier is committed. `/settings` and `/quota` then show unlimited weekly administrator reports. Ordinary accounts cannot configure this identity or gain an exemption through plan/settings commands. Cached or fresh administrator requests still obey the monthly budget and serial-run protection.

## Free shared-report retrieval

Migration 004 adds a service-only shared report cache keyed by the exact investor settings, excluding internal metadata. Shared report text contains property screening results without Telegram identities or previous-view history. `/saved` and `/run` return a fresh exact-setting report before quota checking or dispatch, with no new AI call or quota use. Similar settings share listing research but must be calculated separately; a different loan/equity limit never receives another user's numbers. `/last` remains an unlimited personal report retrieval.

If two users queue identical new requests before the first report exists, the serialized worker publishes the first report and reuses it for the second. The reused job has `usage.shared_hit=true` and is excluded from the weekly quota count. Reports expire with the listing pool and no later than their mortgage sources' permitted age. No unsolicited cross-user messages are sent; automatic delivery still respects weekly opt-in.

The expensive legacy API path is removed. Inactive v2 now produces a zero-cost paused response. Administrator spending messages show the model and a safe failure code. A paid extraction can still fail validation after incurring costs; the ledger keeps those charges and no automatic paid retry occurs. Auxiliary shared-report publishing failures do not discard a valid personal report.

## Research recovery and diagnostics

The initial batch targets 12 complete apartments rather than 20, leaving output room for source-backed fields. A max-output-token response retains only completely decoded JSON fields and array objects; cut-off values/objects are never repaired or invented. Recovered items still require retrieved listing URLs, completed page-open actions, valid price/size and the same finance/radius/exclusion checks. Missing optional sourced rent, owner costs, benchmarks or tax evidence becomes unknown rather than discarding the whole response. Missing geography cannot pass radius screening. Known Freiburg name variants match the same municipality; unrelated city names remain distinct.

An unverified search center returns a prominently labelled partial-research report of verified listing leads, with no eligibility score or investment recommendation. This negative/partial result is cached so another click does not repeat paid research. It is not a successful verified investment shortlist. Complete valid matches recovered from a truncated response are labelled partial coverage.

Job usage now records the rate/listing stage, completion status, incomplete reason, configured output cap, output-text length and a bounded public-data checkpoint with source/opened URLs and fully decoded extraction data. No API keys, raw reasoning or private investor settings are placed in these checkpoints. Evidence is saved before later validation and retained in settlement, allowing offline diagnosis instead of a paid retry. Failures use distinct safe codes, e.g. PoolInvalidJSON or RatesNoRetrievedSources, rather than only ValueError. The old generic failed record cannot establish its exact cause because these diagnostics did not yet exist.


Reports support English (`en`), German (`de`) and Persian (`fa`), selectable with `/set language fa` or the settings buttons. Persian labels, explanations, settings and help are translated in code without an AI translation call. Listing titles and source risk descriptions remain in their original language.

`/run` reuses available research; it does not automatically grow a sparse pool. The administrator can explicitly use `/refresh` to perform a bounded paid search for additional apartments. Existing listings are retained and duplicate URLs removed. The command bypasses saved reports, uses existing mortgage-rate data where current, and obeys the monthly budget/reservation controls. Ordinary users cannot request refreshes. A search target is not a guarantee of finding every public listing.


Private reports first show a compact index of every retained apartment, with price, size, rent, loan/payment and yield where calculable. Listing links open the original advert; Details opens the stored full card in the same chat. Back to list returns to the overview, and Rates & assumptions shows source dates and caveats. The index is delivered in groups of five with navigation links; this is message pagination, not a five-property result cap. `/last` and `/saved` use the same interface. Detail access is limited to the report owner and performs no AI call. Channel posts retain the full plain-text report.

`/help` explains gross yield, loan need, initial annuity, monthly cashflow, maintenance, stress and price per square metre. A dependent result with missing required inputs displays “Missing data”, never a fabricated zero. A genuine zero loan is described as equity covering purchase costs. Known criteria remain checked; unknown criteria are clearly flagged. Incomplete rent/cashflow data receives no displayed numeric score.


The compact index now uses clickable text after gross yield: **Details · Listing**. Details and Back to list are Telegram deep links into this bot, using the same private report-owner checks as older callback buttons. These links never enqueue analysis. The original advert opens through Listing. `TELEGRAM_BOT_USERNAME` may override the public default `MeHousingLoanBot`; set the same value in worker and Edge Function environments when using another bot. No HTML parsing is used: Telegram text-link entities preserve Unicode offsets and safely display listing text.


After accepting the notice, new users enter a seven-step setup guide. `/guide` reopens it: language, search location/limits, financing, investment targets/exclusions, reading reports, schedule/allowance and final review. Settings screens include Continue guide, which resumes the last step after editing. Guide navigation never starts or enqueues research; its final step offers an explicit Run with my settings action. Guide text supports English, German and Persian. Existing users can continue using commands directly.

### Required setup guide
All users, including administrators, must complete the seven-step `/guide` once before manual or weekly analyses. Settings, support and saved reports remain available. Finishing setup does not start paid research. New users see the guide after accepting the notice.

After deploying the updated Telegram Edge Function, run the **Notify all users about required setup guide** workflow manually once. It privately notifies existing users without AI calls; successful notices are deduplicated using negative IDs in `bot_updates` (Telegram update IDs are positive). Blocked chats count as failed. Notice markers expire with the existing 30-day cleanup. Do not run this notification workflow before deploying the new guide completion handler.

### Two-stage listing collection
Fresh collection first discovers individual listing links in one bounded call (up to 4 tools, 3,000 output tokens; no fixed apartment-count target). Links must appear in independently retrieved sources and are canonicalised and deduplicated. Discovery hints are never presented as confirmed apartment facts.

Python stores the public link queue in the existing shared market cache. Small batches of up to five queued URLs are then opened and extracted using a compact schema (5 tools, 4,000 output tokens per batch; a first batch without a verified centre may use 6 tools). Coordinates are stored once per municipality, and missing financial data stays unknown. A batch cannot substitute other apartments for its supplied URLs. Completed attempts leave the queue; incomplete responses retain unprocessed links. All verified apartments are merged with saved apartments without a display cap. Fresh cached queued links are processed before another discovery call.

Verification continues until the queue is exhausted, the cost guard is reached, or the listing tool-call budget is used. There is no fixed apartment-result count. A run permits at most 25 listing tool calls, plus the existing mortgage-rate call when needed. Calls use separate contexts and a five-minute timeout without automatic retries. Optional work stops once accumulated estimated spending reaches $0.80; this stops subsequent calls and does not guarantee the cost of a call already running. Database reservations and the monthly budget remain authoritative. Reports show collection-stage completion and remaining unverified links; neither number represents exhaustive market coverage. Cached `/run` reports remain free; administrator `/refresh` processes additional queued links or discovers new ones when the queue is empty. No SQL migration or Edge Function deployment is required.

### Parameter-driven discovery and retention
Discovery now targets the investor's purchase-price ceiling and minimum size, using the tighter of purchase-price ceiling and loan plus equity as a conservative preliminary price ceiling. Loan payments, rent-based targets and other final criteria remain deterministic checks after extraction; missing optional amounts stay unknown. The shared pool records its search scope: a narrower pool cannot satisfy a broader user's search. Different scopes have different cache keys; broader qualifying pools can still be reused. Query variation covers portals, nearby towns and investment wording within the existing bounded discovery call.

The hourly **Remove expired apartment data** workflow uses no OpenAI key/calls. Seven-day market-cache expiry is enforced by deletion, expired shared reports are deleted, seen URLs older than seven days are removed, and expired job reports/raw property checkpoints are scrubbed. Lightweight job cost, token-usage and status records remain for spending control; settings/access records remain. A cached job report also expires with its underlying data when that expiry is recorded. Cleanup occurs on the next scheduled execution; GitHub scheduling may be delayed. Existing Telegram messages are not deleted. No Supabase migration is required.

### Locked pilot preset
Apply migration `005_locked_pilot.sql` and deploy the updated Telegram Edge Function to activate the shared pilot preset for all current and future users. Freiburg/Germany, 150 km, price and loan €300,000, equity €10,000, minimum 30 m², English, 30-year fixation, no numerical investment targets, exclude leasehold/foreclosure. Initial annual repayment is fixed at 2%, keeping mortgage payment and cashflow estimates available. Weekly reports are enabled Monday 09:00 Europe/Berlin; approved users must still accept the notice and finish the guide. Quotas and the monthly budget remain active. GitHub Actions may deliver after 09:00 because scheduled runners and research take time.

`bot_control.pilot_locked` is the administrative switch. While true, a database trigger enforces the preset and schedule even if a client tries to change them; the webhook displays a lock message. Internal access/guide state is preserved. To later unlock, set the switch false; the pilot defaults remain until deliberately changed. The initial scheduled date is 5 October 2026. This migration does not start paid jobs immediately.

### Restarting the bot spending period
Migration `006_budget_restart.sql` deliberately starts a new spending period with a USD10 API cap. It retains all real charges and token usage, and never resets OpenAI billing. New spending is additional to previous charges. Budget checks retain active/uncertain reservations across the restart, and still pause for uncertain usage. The window rolls forward at the next UTC month boundary. Reapplying the migration deliberately restarts the counter again. USD10 is a conservative API-only cap below EUR10 at the 2 October 2026 reference rate; tax, hosting and exchange fees remain separate.


### Country validation repair
Source-backed German listings accept `Germany`, `Deutschland`, `DE`, `DEU` and explicit federal-republic names; foreign countries remain rejected. Diagnostics now record extraction retention/rejection reasons and report the discovered/newly retained counts. A current refresh no longer inherits a stale truncation flag solely from its older pool. Package-only offers must use the minimum required total package price, not a misleading single-unit quote.

Run **Repair saved research without AI** once in Actions to revalidate fresh, already-paid checkpoints against their retrieved sources and opened URLs. It adds recoverable listings to existing pools, clears stale rendered shared reports, preserves original expiry, and makes no OpenAI call. Unverified, expired and package-only offers with no verified total price remain out. Then `/run` recalculates from the repaired pool without requiring `/refresh`.

### Optional Telegram Stars payments — prepared, not live
Apply migration `007_payments.sql` after 006 and deploy the updated Telegram function. **Every user registered when 007 is applied is permanently marked `pilot_free=true`; future registrations default false.** Administrator access is also exempt. This migration runs once; do not re-run it to capture future customers as pilots.

Target euro prices are €0.99 for one report and €3.96 for a 30-day weekly pass. Telegram digital-service checkout requires integer Stars (`XTR`), whose buyer euro cost varies. Accordingly `report_price_stars` and `weekly_price_stars` start unset and `payments_enabled=false`; no guessed conversion or live charge is installed. Before opening checkout, set the chosen Stars amounts and operator-specific `payment_terms_text`, deploy the function, include `pre_checkout_query` in webhook allowed_updates, and test in Telegram’s payment test environment. Terms must include the actual seller/contact, applicable purchase rights and service conditions; this repository does not certify legal compliance. Payment terms are accepted separately from the general estimates notice.

`/buy` offers one report (no bundled-credit requirement) or a non-renewing 30-day weekly pass. The pass includes every weekly delivery date within its active interval, including a fifth date, without a four-week ceiling; extra manual reports require separate invoices. Additional passes extend from the latest paid pass end. When no active pass exists, paid users’ scheduled runs are skipped. Existing pilot quotas and administrator exemption remain unchanged. Purchasers reopen delivered reports free while the seven-day data retention allows it; unpaid users cannot bypass purchase through a shared saved report. Cached research may be used for a purchased analysis; payment does not guarantee fresh or exhaustive collection, a minimum listing count, or complete optional data.

The webhook validates invoice owner, currency, Stars amount, setup, terms, expiry and settings at pre-checkout. A durable successful-payment event queues exactly one single report, or grants exactly one pass, using Telegram’s unique charge ID. Single-report analysis uses the invoice settings snapshot. Report delivery settles the order; failed/uncertain reports and failed delivery queue full Stars refunds. No automatic paid analysis retry occurs. The hourly **Process pending Stars refunds** workflow continues even when new research is disabled, needs no OpenAI key and also reconciles interrupted terminal settlements. Ambiguous refund API failures remain pending and notify the administrator rather than claiming money was returned.

`/terms`, `/paysupport QUESTION`, admin `/payments` and admin `/refund ORDER_UUID` are implemented. A pass refund revokes that pass’s remaining weekly access; already completed reports remain saved until normal retention expiry. The pass has no auto-renewal and manual refunds are full-order refunds. Records retain charge identifiers and accounting metadata; temporary single-order settings snapshots are scrubbed after fulfillment/refund. Payment receipt records are distinct from the public apartment-data cleanup.

### Rental pilot (migration 008)

Choose `/service` first: investment or whole-apartment rental. Investment selection offers the latest delivered administrator **weekly** report as a free preview; it never exposes another customer's report. If none exists within seven days, the bot says so instead of starting paid research.

Rentals have separate settings: location in Germany, radius (0–300 km), and maximum advertised total monthly rent (`max_rent_eur`, Warmmiete). `/settings` has editing buttons; `/run` creates the first free rental report; `/last` reopens a saved rental report. `/daily on|off` controls 09:00 Europe/Berlin delivery. Existing pilot users and the administrator remain exempt. Ordinary users receive one free delivered rental report, with at most one attempt per Berlin calendar date; failed attempts do not consume the trial. After a completed report with failed delivery, `/last` recovers it for free. The hourly worker may deliver later than 09:00 if Actions is delayed.

Rental collection uses dedicated rental instructions, opens individual listing pages and never runs mortgage research. Every retained match is paginated without a display cap. Missing rent is not zero; unknown total rent or distance is explicitly provisional. The same exact search is shared for 24 hours. Fresh research reopens listings; older availability is not silently treated as verified today. Separate electricity/internet may not be included in advertised Warmmiete. Search calls, output and global spending are bounded, and incomplete coverage is disclosed. Public rental cache and report evidence expire after seven days; cost records remain.

**Rental payments are not implemented/open in this pilot.** The intended choices are 1, 5, 10 or 30 days, but rental prices remain unset and no rental checkout occurs. New non-pilot users stop after the free report until packages are implemented and prices are configured. `/rentalcost` (administrator only) measures estimated API spend per delivered report including settled failures and shared-cache hits. Buyer Star prices are not merchant proceeds; determine net reward proceeds and hosting/tax/refund costs before choosing profitable prices. Never reset real billing records to hide spend.

Deployment: apply `supabase/migrations/008_rental_pilot.sql` once, then replace/deploy the Telegram Edge function. Leave JWT verification OFF and the webhook secret unchanged. Only after both steps, enable the rental pilot with `update bot_control set rental_enabled=true where id=1;`. Existing investment settings, prices and pilot exemptions are preserved.
