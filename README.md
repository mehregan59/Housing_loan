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

No always-running laptop is required. The legacy worker uses `gpt-6-astra`. The v2 extractor defaults to `gpt-6.1-sol` (`RESEARCH_MODEL`), supporting web search and structured outputs. Python performs calculations and writes reports. There is no automatic paid fallback to a more expensive model. Model/pricing configuration must be reviewed before changing it. The pilot has a separate $8 OpenAI project hard cap and a database budget of $8, chosen as a conservative allowance under the operator's €10 goal. Currency conversion, taxes and hosting are separate. $1/job is a **budget reservation, not a guaranteed maximum bill**: search-input token costs cannot be known precisely before the response completes. The OpenAI hard limit is the billing backstop and can slightly overshoot during propagation.

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

Free membership permits one analysis/week, paid seven. Scheduled reports count too. Reset Monday 00:00 Europe/Berlin. The pilot initially approves only the configured administrator, without committing their ID. Admin commands: `/approve ID`, `/plan ID free|paid`, `/reply ID MESSAGE`, `/cost`, `/channel on|off`. Optional channel/group posting shares only the admin's reports and requires a GitHub `CHANNEL_ID` secret and bot posting permissions. Payments are not collected automatically during this pilot.

Schedules are checked hourly at minute 17 UTC. Delivery can be up to an hour later plus GitHub queue delay; due slots can catch up within 24 hours. Local timezones use DST rules. GitHub scheduled workflows in public repositories can be disabled after 60 days without repository activity; watch the Actions page. Database health checks do not remove that GitHub limitation.

## Analysis and uncertainty

V2 aims to collect 20 distinct apartments (maximum 30 extracted) per shared German location/radius pool, without investor financial limits. Portals and local agents are searched; individual pages must have a retrieved source URL and a recorded page-open action. This is a target, never a guarantee. At most eight strict matches are shown, plus three clearly labelled flexibility options when fewer than five strict matches exist. Reports may span several Telegram messages. No synthetic listings fill gaps.

Data is cached for seven days, refreshing saved URLs first when expired. Financing is shared by fixed-rate period and requires two independent, dated nominal-rate sources no more than 14 days old. Effective APR is not substituted in monthly-interest arithmetic. Empty research results are also cached to prevent repeated paid searches. The cache contains public research only, never private investor settings. Locations within 5 km can reuse a pool only when sourced municipality coordinates prove that its radius covers the request. Approximate town-center distances are disclosed. Additional areas rank preferred towns within the radius; they do not expand coverage.

Required loan = price × (1 + state transfer tax + estimated 2% notary/registry + stated buyer commission) − equity, never silently capped. Missing commission/tax leaves financing unknown and prevents confirmed matches. Monthly initial payment = loan × (nominal interest + initial repayment) / 1200. Gross yield = monthly cold rent × 1200 / price. Monthly result subtracts the mortgage, owner-only operating building fees excluding reserve contributions, and €1/m² maintenance. This is initial annuity screening, not full repayment within the fixed-rate period.

Actual and estimated rent/owner costs have source links. Estimates require a cited relevant basis; area alone does not justify building fees. Missing costs without reliable comparable evidence stay unknown. Major repairs/assessments are never invented. Recommendations enforce hard limits; flexibility options may differ by at most 10% on price, size, radius, loan, price/m² or yield, or €50/month on the cashflow target, with at most two differences. Exclusions and Germany are never relaxed. A higher loan requirement is explicitly labelled not financeable under the current cap; settings are never changed.

The fixed screening rubric starts at 2 points, adds up to 4 for gross yield (yield/2), 2 for nonnegative monthly results, and 1 for nonnegative stressed results; it subtracts 1 for energy E–H and 1 for unknown/estimated owner costs, then clamps to 0–10. New homes and preferred towns rank first, followed by this score and monthly result. Scores are subjective screens, not predictions. Source/shape checks cannot prove extracted amounts, stated availability or municipal coordinates are correct. Compare initial live results with listings before inviting a larger audience.

Public-facing notice: estimates only; general information, not financial advice or a financing commitment. Users must verify before deciding. The notice does not eliminate statutory operator obligations or liability. Before a public commercial launch, provide appropriate operator contact/imprint, privacy information and service terms reviewed for the actual service. No public paid launch is implemented here.

## Cost and recovery

Quota and budget reservations are atomic in PostgreSQL. Only one active job per user is permitted. Worker claims are atomic and check approval, acceptance, activation and global spending again. Click/webhook duplicates reuse one request record. Output tokens, built-in tool calls, timeout and automatic SDK retries are bounded; retries are disabled. V2 makes at most two research calls on an empty cache (four rate-tool calls and 24 listing-tool calls; output limits 1,500/14,000 tokens). It sends no investor finances or seen-URL histories to OpenAI. A complete cache hit costs $0 in OpenAI API usage; hosting remains separate. Costs include token usage, conservatively counted tool actions, legacy container sessions if applicable, and a 10% estimate buffer. Fresh-research cost is not guaranteed in advance. They are not official invoices.

V2 queues cached work with zero reservation and acquires a locked $1 research reservation before paid calls. Exhausted monthly search budgets block fresh research, while fresh cached reports can still run. The existing approval and weekly report quotas remain enforced for cached work. Unknown usage or an interrupted running job pauses new analyses pending admin reconciliation. Failed jobs with known positive usage still count toward quota. Report delivery failure keeps the completed report for `/last`, without rerunning the paid analysis. Failed dispatch leaves a queued job for the next scheduled sweep.

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

Only an administrator can send `/plan ID paid` to allow seven reports/week, or `/plan ID free` to return to one. Changing settings and `/last` cost no OpenAI tokens. Cached reports still count toward the weekly report allowance.

## Shared-research upgrade

See the staged upgrade steps at the end of [SETUP.md](SETUP.md). Migration 002 preserves existing settings, reports and permissions and leaves `research_v2=false`. Do not rerun migration 001. No paid test is performed by applying the migration.
