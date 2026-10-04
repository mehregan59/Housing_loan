# Housing Loan Bot

Invite-only Telegram pilot for screening German buy-to-let apartments. Users choose a German city, search radius, financial limits, language and a weekly schedule. Other countries can be added later through country-specific taxes, financing and rental rules; changing the country is not enabled in this release.

**Status:** implementation prepared; not deployed or live-tested. Analysis and health workflows are disabled until explicitly enabled. No API call is made by the offline test workflow.

## Services

| Service | Role |
| --- | --- |
| Supabase | Private settings, jobs, quotas, cost ledger and Telegram webhook |
| GitHub Actions | Longer OpenAI analysis and scheduled report processing |
| OpenAI Responses API | Web search and Code Interpreter |
| Telegram | Buttons, commands, reports and support |

No always-running laptop is required. The worker defaults to `gpt-6-astra`, supporting both tools. Model/pricing configuration must be reviewed before changing it. The pilot has a separate $8 OpenAI project hard cap and a database budget of $8, chosen as a conservative allowance under the operator's €10 goal. Currency conversion, taxes and hosting are separate. $1/job is a **budget reservation, not a guaranteed maximum bill**: search-input token costs cannot be known precisely before the response completes. The OpenAI hard limit is the billing backstop and can slightly overshoot during propagation.

## User commands

- `/start`: information notice and explicit acceptance.
- `/help`: command examples, allowances and failure guidance.
- `/settings`: readable summary with buttons for individual settings. Tap a field, send a new value, and receive confirmation. `/cancel` exits; unanswered edits expire after 15 minutes. Language, day, exclusions and weekly on/off use selection buttons. No AI call is made for editing settings.
- `/set FIELD VALUE`: optional command shortcut for experienced users.
- `/location CITY`, `/areas CITY, CITY`: German search locations.
- `/exclude Erbpacht, Zwangsversteigerung`; `none` clears exclusions.
- `/schedule mon 08:00 Europe/Berlin`: editable weekday/time/timezone.
- `/weekly on|off`: enable automatic delivery (initially off).
- `/run`: request new analysis, also available as a button.
- `/quota`: remaining weekly allowance; `/last`: latest saved report without a new API call.
- `/disclaimer`: estimates and data-use notice.
- `/support QUESTION`: forward question and Telegram ID to administrator; manual response, no AI cost.

Free membership permits one analysis/week, paid seven. Scheduled reports count too. Reset Monday 00:00 Europe/Berlin. The pilot initially approves only the configured administrator, without committing their ID. Admin commands: `/approve ID`, `/plan ID free|paid`, `/reply ID MESSAGE`, `/cost`, `/channel on|off`. Optional channel/group posting shares only the admin's reports and requires a GitHub `CHANNEL_ID` secret and bot posting permissions. Payments are not collected automatically during this pilot.

Schedules are checked hourly at minute 17 UTC. Delivery can be up to an hour later plus GitHub queue delay; due slots can catch up within 24 hours. Local timezones use DST rules. GitHub scheduled workflows in public repositories can be disabled after 60 days without repository activity; watch the Actions page. Database health checks do not remove that GitHub limitation.

## Analysis and uncertainty

The prompt requires current financing sources and individually found listing URLs, German state-specific purchase taxes, initial-annuity calculations in Code Interpreter, actual/estimated rent distinctions and unknown-cost warnings. Required financing includes purchase costs and is never silently capped to manufacture affordability. Null cashflow/yield targets do not filter properties. Zero equity is a search assumption, not evidence a bank would finance all costs.

The worker rejects listing URLs absent from retrieved sources and recommendations without a completed calculation tool. These checks cannot prove every figure, URL's live availability or calculation is correct. Verify reports manually. Listing coverage is partial, scores subjective, and taxes/vacancy/exceptional costs are not all included in cashflow.

Public-facing notice: estimates only; general information, not financial advice or a financing commitment. Users must verify before deciding. The notice does not eliminate statutory operator obligations or liability. Before a public commercial launch, provide appropriate operator contact/imprint, privacy information and service terms reviewed for the actual service. No public paid launch is implemented here.

## Cost and recovery

Quota and budget reservations are atomic in PostgreSQL. Only one active job per user is permitted. Worker claims are atomic and check approval, acceptance, activation and global spending again. Click/webhook duplicates reuse one request record. Output tokens, built-in tool calls, timeout and automatic SDK retries are bounded; retries are disabled. Costs include token usage, searches, 1 GB container sessions and a 10% estimate buffer. They are not official invoices.

Unknown usage or an interrupted running job pauses new analyses pending admin reconciliation. Failed jobs with known positive usage still count toward quota. Report delivery failure keeps the completed report for `/last`, without rerunning the paid analysis. Failed dispatch leaves a queued job for the next scheduled sweep.

Admin reconciliation: inspect OpenAI billing for the job time; record verified `charged_usd` and change an `uncertain` job to `failed` in Supabase. Never erase an uncertain reservation or retry blindly. Costs can be incurred even when no report is delivered.

Daily health checks verify database access and overdue queued jobs, update one bounded health record and alert the admin. They do not call OpenAI and **do not guarantee** that Supabase Free will avoid pausing. No automatic restore is implemented. Support forwarding is best effort; retries after uncertain Telegram delivery can duplicate a support notification.

## Tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

GitHub's offline workflow also checks TypeScript and runs the migration plus quota/budget tests on disposable PostgreSQL. It does not use production secrets or make paid requests. See [SETUP.md](SETUP.md) for staged deployment instructions.

License: [LICENSE](LICENSE).
