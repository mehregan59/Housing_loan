# Freiburg Apartment Investment Agent

An AI agent that scans the apartment market in and around Freiburg im Breisgau every week, estimates financing using current market interest rates, scores each listing as a buy-to-let investment, and posts a summary to a Telegram channel.

> ⚠️ **Disclaimer: estimates only, no promise.**
> All figures (interest rates, loan amounts, monthly rates, rents, yields, cashflow, scores) are **estimates** generated automatically by an AI model from publicly available information. They are **not a promise or guarantee** of any loan, interest rate, rent, return or property value, and not a loan offer, financing commitment, bank assessment, or financial, tax or legal advice. Listings may be outdated or inaccurate. Always verify everything yourself and consult your bank or a qualified advisor before making any decision. Any decision is made at your own risk. See section 6 of [LICENSE.md](LICENSE.md).

---

## What it does

Every week (default: Monday 08:00 Europe/Berlin) the agent:

1. **Checks financing conditions:** looks up this week's average German mortgage rates for your fixed-rate period from several public sources and uses the midpoint plus a stress scenario.
2. **Finds listings:** searches for apartments for sale in Freiburg and the surrounding towns you choose, skipping listings it has already reported.
3. **Calculates:** purchase side costs (Baden-Württemberg), loan amount, monthly rate, rent (actual or estimated), gross yield and monthly cashflow. All arithmetic runs in a code tool, not in the model's head.
4. **Judges:** scores each listing 0–10 against your personal limits and flags the main risks (energy class, Hausgeld, Erbpacht, rent regulation, vacancy).
5. **Reports:** posts the top 5 listings to your Telegram channel.

---

## How it works

```
GitHub Actions (weekly schedule)
        │
        ▼
   agent.py ──► OpenAI Responses API
        │          ├─ web_search        (rates + listings)
        │          └─ code_interpreter  (all calculations)
        ▼
 Telegram Bot API ──► your channel / group
        │
        ▼
 seen_urls.json  (committed back to the repo so listings aren't repeated)
```

No server or hosting is needed. GitHub Actions starts the agent on schedule and shuts it down when finished.

---

## Repository structure

```
.
├── .github/workflows/weekly.yml   # schedule + run job
├── agent.py                       # main script
├── prompt.txt                     # system prompt for the AI agent
├── settings.json                  # your investment limits (edit this)
├── seen_urls.json                 # listings already reported (auto-updated)
├── requirements.txt
├── README.md
└── LICENSE.md
```

---

## Setup

### 1. Create the Telegram bot

1. In Telegram, open **@BotFather** and send `/newbot`.
2. Choose a name and username. Copy the **bot token**.
3. Create a Telegram **channel** (or group) and add the bot as an **administrator** with permission to post messages.
4. Get the channel ID: for a public channel use `@yourchannelname`. For a private channel, forward a message from it to **@userinfobot** or a similar bot and copy the numeric ID (starts with `-100`).

### 2. Get an OpenAI API key

1. Create a key at platform.openai.com → API keys.
2. **Set a monthly spending limit** under Billing → Limits. Use a key dedicated to this project.

### 3. Add GitHub secrets

In your repository: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name          | Value                                   |
|----------------------|-----------------------------------------|
| `OPENAI_API_KEY`     | your OpenAI API key                     |
| `TELEGRAM_BOT_TOKEN` | the token from BotFather                |
| `TELEGRAM_CHAT_ID`   | `@yourchannel` or `-100…` numeric ID    |

Never put keys in `settings.json` or any committed file.

### 4. Allow the workflow to save seen listings

**Settings → Actions → General → Workflow permissions → Read and write permissions → Save.**

### 5. Test it

**Actions → Weekly apartment report → Run workflow.** A report should appear in your Telegram channel within a few minutes.

---

## Settings

Edit `settings.json` directly on GitHub (works from your phone). Changes apply on the next run.

```json
{
  "language": "de",
  "max_loan_eur": 350000,
  "equity_eur": 80000,
  "max_price_eur": 400000,
  "min_size_m2": 40,
  "max_price_per_m2": 6000,
  "target_gross_yield_pct": 4.0,
  "min_monthly_cashflow_eur": -150,
  "fixed_rate_years": 10,
  "repayment_pct": 2.0,
  "areas": ["Freiburg", "Gundelfingen", "Merzhausen", "Umkirch", "Kirchzarten", "Denzlingen"],
  "radius_km": 15,
  "exclude": ["Erbpacht", "Zwangsversteigerung"],
  "max_results": 5
}
```

| Field | Meaning |
|-------|---------|
| `language` | Report language (`de` or `en`) |
| `max_loan_eur` | Maximum loan you are willing or able to take |
| `equity_eur` | Own capital available (Eigenkapital) |
| `max_price_eur` | Maximum purchase price |
| `min_size_m2` | Minimum living area |
| `max_price_per_m2` | Maximum price per square metre |
| `target_gross_yield_pct` | Target gross rental yield (annual cold rent / price) |
| `min_monthly_cashflow_eur` | Lowest acceptable monthly cashflow (can be negative) |
| `fixed_rate_years` | Fixed interest period (Zinsbindung) used for rate lookup |
| `repayment_pct` | Initial repayment rate (anfängliche Tilgung) |
| `areas` | Towns / districts to search |
| `radius_km` | Search radius around Freiburg |
| `exclude` | Listing types to skip |
| `max_results` | Number of listings per report |

### Changing the schedule

Edit the `cron` line in `.github/workflows/weekly.yml`. Times are in **UTC**:

```yaml
on:
  schedule:
    - cron: "0 6 * * 1"   # Monday 06:00 UTC = 08:00 Berlin (summer time)
  workflow_dispatch:       # allows manual runs
```

---

## Costs

| Item | Cost |
|------|------|
| GitHub Actions | Free for this usage (private repos include free minutes) |
| Telegram | Free |
| OpenAI API | Pay per use. Web search calls are the main cost. Expect a small amount per weekly run; check your usage dashboard after the first runs |

Set an OpenAI spending limit before the first run.

---

## Limitations

- **Coverage is partial.** Major listing portals restrict automated access, so the agent sees a sample of the market found via web search, not every listing.
- **Estimates, not facts.** Missing values (rent, Hausgeld, year built) are estimated and labelled as such in the report.
- **Interest rates are averages.** Your actual bank offer depends on your income, credit history, the property and the lender.
- **AI can be wrong.** Check at least one listing per report by hand, especially in the first weeks.

---

## Upgrade path

If several people need their own settings, the agent can move to a small always-on server (e.g. a Hetzner VPS) with Telegram bot commands such as `/set max_loan_eur 300000`. The analysis logic and prompt stay the same.

---

## License

Proprietary. All rights reserved. See [LICENSE.md](LICENSE.md). Any use, copying, or commercial use requires a written license from the copyright holder.
