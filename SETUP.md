# Staged setup — do one stage at a time

The code is prepared, not deployed. Keep Actions variables `BOT_ENABLED` and `HEALTH_ENABLED` unset and `bot_control.enabled=false` until instructed to activate. Existing API/bot secrets are not read by the offline tests.

## 1. Database (next user step)

Open your Supabase project's SQL Editor. Paste [supabase/migrations/001_bot.sql](supabase/migrations/001_bot.sql) and run it **once**. This adds only `bot_*` tables and functions. It does not seed a personal Telegram ID or start an analysis. Stop and confirm before continuing.

## 2. Secrets

GitHub Settings > Secrets and variables > Actions must contain:

- `OPENAI_API_KEY`: dedicated Housing Loan project key, with enforced $8 monthly spend limit.
- `TELEGRAM_BOT_TOKEN`: @MeHousingLoanBot token.
- `ADMIN_USER_ID`: operator's numeric Telegram ID.
- `SUPABASE_URL`: `https://liukclxefiqqrgyuoyrx.supabase.co`.
- `SUPABASE_SECRET_KEY`: newer `sb_secret_...` backend key. The worker sends it on the `apikey` header, not as a bearer JWT.

No privileged keys, user settings or reports belong in this public repository.

## 3. Deploy short Telegram function

Deploy `supabase/functions/telegram/index.ts` as an Edge Function named `telegram`. Set JWT verification **off** for this function: Telegram authenticates through `X-Telegram-Bot-Api-Secret-Token`, verified in the code. Do not remove that check.

Set function secrets:

- `TELEGRAM_BOT_TOKEN` and `ADMIN_USER_ID` as above.
- `TELEGRAM_WEBHOOK_SECRET`: newly generated random secret, 32+ characters, stored privately.
- `BOT_DATABASE_KEY`: your Supabase secret key. Alternatively code uses the platform-supplied service-role key. Do not try to set reserved `SUPABASE_*` variable names manually.
- `GITHUB_REPOSITORY`: `mehregan59/Housing_loan`.
- `GITHUB_DISPATCH_TOKEN`: fine-grained GitHub token limited to this repository with **Actions: read/write**; expiry and renewals monitored by operator. Users never receive it.

CLI alternative (local secrets entered privately, not committed): `supabase functions deploy telegram --project-ref liukclxefiqqrgyuoyrx --no-verify-jwt`. CLI deployment requires Supabase account authorization, separate from the database secret key.

## 4. Register webhook

Call Telegram `setWebhook` from a private local script or terminal, using the bot token, with:

- URL `https://liukclxefiqqrgyuoyrx.supabase.co/functions/v1/telegram`
- `secret_token`: exactly the function's `TELEGRAM_WEBHOOK_SECRET`
- `allowed_updates`: `["message","callback_query"]`

Do not put the bot token in a shared browser URL or screenshot. Set description to “German property screening with estimated financing. General information, not financial advice. Verify before deciding.” Set bot commands from the README. Open the bot, `/start`, accept the notice, and test `/help`, `/settings`, `/schedule`, `/support`. These steps make no OpenAI call.

## 5. Activation — after explicit confirmation

Verify offline tests pass, all settings match the operator's choices and the OpenAI hard cap is enforced. Set `bot_control.enabled=true` in Supabase; set GitHub Actions variable `BOT_ENABLED=true`. Run `/run` once and verify sources, figures and estimated costs. This is the first paid API request.

After confirming that report, send `/weekly on`. Default Monday 08:00 Europe/Berlin is editable with `/schedule`. The database remains authoritative for weekly quotas and the global $8 budget. Set `HEALTH_ENABLED=true` to enable daily database health checks; this makes no OpenAI call and does not guarantee prevention of Supabase pausing.

Stop spending immediately by setting `bot_control.enabled=false` and `BOT_ENABLED=false`; already-running OpenAI requests may still incur charges. Do not enable public registration or collect payments in this pilot. Admin membership grants are manual.
