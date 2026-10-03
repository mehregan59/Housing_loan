# Telegram agent pilot setup

Status: setup checklist only; the agent is not deployed or operational yet.

## Architecture

- Supabase project `liukclxefiqqrgyuoyrx`: private user settings, memberships, weekly quotas, analysis jobs, listing history and cost ledger.
- Supabase Edge Function: receives verified Telegram webhook requests, handles commands and buttons, reserves quotas atomically and dispatches GitHub Actions.
- GitHub Actions: runs the longer OpenAI analysis and sends results through Telegram.
- Free users: one analysis per week. Paid users: seven. Automatic weekly reports count toward these allowances. Start invite-only, with memberships assigned manually by the admin.
- Weekly reset: Monday 00:00 Europe/Berlin. Intended report time: Monday 08:00 Europe/Berlin; handle daylight saving and delayed Actions jobs without duplicate reports.
- Daily maintenance workflow: check database connectivity and overdue jobs, record bounded health status and alert the administrator. No OpenAI call. This may reduce inactivity risk but does not guarantee exemption from Supabase Free project pausing.

## GitHub Actions secrets

Enter values at Settings > Secrets and variables > Actions. Never commit credentials or paste them into chat.

| Name | Value |
| --- | --- |
| OPENAI_API_KEY | Dedicated project key with enforced OpenAI spending cap |
| TELEGRAM_BOT_TOKEN | Token from @BotFather |
| ADMIN_USER_ID | Admin numeric Telegram user ID; private cost-report recipient |
| SUPABASE_URL | https://liukclxefiqqrgyuoyrx.supabase.co |
| SUPABASE_SERVICE_ROLE_KEY | Privileged backend service-role key; implementation must support the selected Supabase credential type |
| CHANNEL_ID | Optional group/channel destination |

The publishable key alone cannot administer the database or deploy functions. Enable RLS on private bot tables and deny public direct access. Do not use privileged keys in frontend code.

## Supabase Edge Function secrets

- TELEGRAM_BOT_TOKEN
- ADMIN_USER_ID
- TELEGRAM_WEBHOOK_SECRET: random value for validating incoming Telegram webhook requests.
- GITHUB_DISPATCH_TOKEN: fine-grained token restricted to this repository, with Actions write permission; a GitHub App credential can replace it later.
- GITHUB_REPOSITORY: mehregan59/Housing_loan

Verify the backend credential environment provided by Supabase during deployment.

## Remaining user choices

- Monthly API budget in USD and maximum cost exposure per run.
- Initial investment settings and language, editable by each registered user.
- Telegram bot username and pilot user allowlist.
- Optional channel posting; default delivery is private.

## Implementation and activation

1. Create the Telegram bot with @BotFather and open its private chat.
2. Store secrets in dashboards.
3. Implement and review SQL migration, RLS and atomic quota/job reservations.
4. Apply migration through Supabase SQL Editor; deploy webhook function.
5. Implement analysis worker, prompt, usage ledger, tests and workflow files.
6. Test commands, quotas and retries with mocked analysis before spending API credits.
7. Register Telegram webhook with a secret token. Verify authentication and user identity.
8. Run one real analysis and inspect source URLs, arithmetic, Telegram delivery and cost reporting.
9. Enable the weekly schedule and daily health check. Review first three reports before opening registration.

## Cost and reliability requirements

- Validate identity, quota and spending allowance in the webhook and again in the worker.
- Prevent duplicate requests caused by repeated clicks or Telegram retries.
- Bound input history, output tokens, tool calls, retries and runtime. A client timeout alone does not guarantee server-side cancellation or prevent charges.
- Reserve estimated budget before API calls; account for failed attempts and unknown usage conservatively.
- Include model tokens, web-search fees and Code Interpreter containers in estimated costs. Send cost notifications privately to the administrator; hosting is separate.
- Recover failed dispatches and stale jobs explicitly, without blindly repeating paid requests.
- Never commit per-user financial settings, report history, database exports or secret tokens to this public repository.

The existing README describes an earlier single-channel design. This checklist records the agreed multi-user pilot; implementation and documentation must be reconciled before launch.
