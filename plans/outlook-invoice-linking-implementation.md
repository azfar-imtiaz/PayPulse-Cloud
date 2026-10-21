# Outlook/Microsoft Graph Email Linking — Implementation Plan

## Implementation rules

1. Implement this plan step by step. Each step must be tested and committed before moving on to the next one.
2. While or after implementing a step, test the functionality as thoroughly as possible in isolation before considering it complete — don't move to a later step only to discover a bug in an earlier one.
3. Before starting implementation of a step, check current docs/methods online to confirm the plan is still aligned with the latest Microsoft Graph / MSAL guidance — avoid building against a deprecated API only to find out at test time.
4. If any question comes up during implementation, pause and ask the user before proceeding. Do not guess past an open question.

## Context

PayPulse-Cloud currently links Gmail via `gmail_store_tokens` + `fetch_and_classify_retail_invoices`, sweeping the user's inbox on a cron, classifying candidate emails (Jev → Gemini fallback), and writing confirmed retail invoices to S3 (triggering the existing, unchanged parse/classify/DynamoDB pipeline). The goal is to add Outlook/Microsoft Graph as a second email provider feeding the *same* downstream pipeline, so users who use Outlook instead of (or alongside) Gmail get the same automatic invoice capture.

The one-time manual Entra app registration is done — Application (client) ID `6861aa59-75ec-4dac-883e-0f9b96aa6576`, tenant `common`, public client, redirect URI `msauth.com.azfarimtiaz.paypulse://auth`. This plan covers the backend implementation that follows.

## Decisions

1. **Sweep schedule**: reuse Gmail's existing `retail_sweep_trigger` EventBridge rule, adding a second `aws_cloudwatch_event_target` pointing at the new Outlook fetch Lambda, rather than creating a separate rule. (A separate rule's only real advantage is decoupled blast radius/debugging — not considerable enough to justify the extra resource given both sweeps start on the same cadence anyway.)
2. **Gmail's dead S3-folder-creation bug** (wrong function name + missing `S3_BUCKET` env var in `lambda_gmail_store_tokens.tf`): fix it, since this Outlook work is already touching the same area — but as its **own separate commit**, not bundled into any Outlook-feature commit.
3. **`determine_sweep_date_range` duplication**: duplicate the logic in the new Outlook fetch Lambda rather than extracting it to a shared layer util — matches the existing codebase's preference for per-Lambda duplication.

## New files

Each subsection below starts with a one-line **What/why** before the implementation detail.

### `lambdas/auth/outlook_store_tokens/main.py`
**What/why**: the API endpoint the iOS app calls right after the user finishes Microsoft sign-in. It takes the tokens the iOS MSAL SDK obtained client-side and persists them server-side so later backend jobs (the sweep Lambda) can use them without the user being present. This is the Outlook equivalent of "link my Gmail account."

Mirrors `lambdas/auth/gmail_store_tokens/main.py` (`@require_auth`, same body-parsing block for base64/form/json). Required: `access_token`. Optional: `refresh_token`, `expires_in` (default 3600), `scope`.
- `validate_oauth_tokens(access_token, scope)` — reuse; verify during implementation it isn't Google-scope-hardcoded (check `oauth_utils.py`) — if it is, add an inline Outlook scope check for `Mail.Read` + `offline_access` instead of forking the function.
- New `get_outlook_user_info(access_token)` in `oauth_utils.py` — Graph `GET /v1.0/me`, maps to `{outlook_user_id, outlook_email, outlook_name}`.
- New `validate_outlook_account_consistency(user_id, new_outlook_user_id, new_outlook_email, region)` in `oauth_utils.py`, mirrors `validate_google_account_consistency`.
- New `store_outlook_oauth_tokens(...)` (see Secrets Manager section).
- S3 folder creation: call `create_user_folders_in_s3(s3_client, user_id, S3_BUCKET)` — the correct plural name. Wire `S3_BUCKET` env var in this Lambda's Terraform so the call path actually runs.
- Response/error-handling shape identical to Gmail's (`success_response(..., status_code=201)`; `(URLError, HTTPError)`→502, `OAuthValidationError`→400, `SecretsManagerError`→502, `json.JSONDecodeError`→400, `KeyError`→400, generic→500).

### `lambda_layers/common/python/utils/outlook_api_utils.py` (new, mirrors `gmail_api_utils.py`)
**What/why**: the shared toolkit for talking to Microsoft Graph — getting a usable access token (refreshing if expired), listing candidate emails in a date range, and pulling an email's content. This is what the sweep Lambda calls each run; it owns the one genuinely new, provider-specific risk in this feature (Microsoft invalidates your refresh token every time you use it, unlike Google) — getting that right here means every caller downstream is automatically safe.

- `create_outlook_client(user_id, access_token, refresh_token, client_id, region, expires_at=None)` — plain `requests` against `https://graph.microsoft.com/v1.0` (no SDK/new layer needed — Graph is REST). Expiry check mirrors Gmail's (`dateutil.parser.isoparse`, refresh if <5 min left).
  - Refresh: `POST https://login.microsoftonline.com/common/oauth2/v2.0/token`, `grant_type=refresh_token`, public client (no secret).
  - On `invalid_grant` → `delete_outlook_oauth_tokens` + raise `RefreshTokenExpiredError`.
  - **Critical, must get right**: Microsoft rotates the refresh token on every refresh. The new `refresh_token` from Microsoft's response must be written via `update_outlook_oauth_tokens(...)` unconditionally — never fall back to the old token (unlike Gmail's safe `credentials.refresh_token or refresh_token` pattern). If Microsoft's response is missing `refresh_token`, treat it as a hard error (raise `OAuthValidationError`), not a silent reuse.
    - **Verified live against a real consumer Microsoft account (2026-10-21)**: reusing an already-rotated OLD refresh token still succeeded and issued yet another new token pair — Microsoft does NOT guarantee the old token is invalidated immediately, matching the official docs ("the authorization server MAY revoke the old refresh token"). This means `invalid_grant` is NOT a reliable signal that "this old token was reused" — don't build any logic that assumes a reused-old-token case will always fail. It only matters that we always store Microsoft's latest-returned token; whether the prior one also still works briefly is Microsoft's call, not something to detect or handle.
  - Other non-2xx → raise new `OutlookAPIError` (add to `exceptions.py`).
- `build_sweep_outlook_query(start_date, end_date, excluded_senders=None)` — Graph OData `$filter` equivalent of Gmail's sweep query.
- `list_messages(client, query_filter, page_url=None)` — pages via `@odata.nextLink`, same `(messages, next_link_or_None)` contract as Gmail's pagination.
- `get_email_metadata_light(client, message_id)` / `get_message_content(client, message_id)` — lightweight vs full fetch, mirrors Gmail's two-stage cost optimization. Graph returns body as `body.content`/`body.contentType` directly — add tiny `extract_html_from_outlook_message(message_json)` helper (near no-op compared to Gmail's MIME walk).
- `derive_vendor_slug_from_sender(from_field)` — adapt Graph's `from.emailAddress.address` shape into the same string format Gmail's existing regex-based slug function expects, and reuse that function rather than duplicating the regex.

**Correction**: the `provider` tag (`'outlook'`) is added via `upload_html_to_s3(..., metadata={'provider': 'outlook', ...})`'s `metadata` dict (`s3_utils.py:198`, already accepts an optional dict) — NOT via `generate_retail_invoice_s3_key(...)` (`s3_utils.py:131`), which only builds a string key and has no metadata param.

### `lambda_layers/common/python/utils/secretsmanager_utils.py` — add functions (same file, not a new one)
**What/why**: where the linked account's tokens actually live at rest, namespaced by provider (`outlook/user/{user_id}` vs `gmail/user/{user_id}`). Both the store-tokens Lambda and the sweep Lambda read/write through these functions — this is the single source of truth for "is this user's Outlook connected, and with what tokens."

Add `store_outlook_oauth_tokens`, `get_outlook_oauth_tokens`, `update_outlook_oauth_tokens`, `delete_outlook_oauth_tokens`, each identical in shape to the Gmail equivalents but keyed on secret name `outlook/user/{user_id}`. Keeping them in the same file avoids duplicating boto3/error-handling logic that would otherwise drift. `update_outlook_oauth_tokens` is the one call site enforcing the rotation-overwrite rule above.

### `lambda_layers/common/python/utils/exceptions.py`
Add `OutlookAPIError` (mirrors `GmailAPIError`). Reuse `RefreshTokenExpiredError`, `OAuthValidationError`, `SecretsManagerError` as-is.

### `lambdas/invoices/fetch_and_classify_outlook_invoices/lambda_function.py` (new, mirrors `fetch_and_classify_retail_invoices/lambda_function.py`)
**What/why**: the actual sweep job — runs on a schedule (and on-demand for backfill), scans each linked user's Outlook inbox for new emails since the last run, classifies which ones are retail invoices, and drops the confirmed ones into S3 so the existing parsing pipeline picks them up. This is the Lambda doing the ongoing work; everything above it just sets up the one-time account link it depends on.

Function-for-function mirror:
- `determine_sweep_date_range(...)` — duplicated (per decision above), using a **separate** checkpoint field `last_outlook_sweep_fetch` on the Users table (independent of Gmail's `last_retail_sweep_fetch`).
- `list_sweep_candidates(outlook_client, ...)` — pages via `@odata.nextLink`, same `(message_ids, exhausted_bool)` contract and page-cap safety net (`MAX_SWEEP_PAGES`).
- `process_candidate_email(...)` — same ledger-dedupe → classify (Jev/Gemini, reused as-is) → upload shape. Swap in Outlook's metadata/content fetchers. Downstream of "confirmed candidate," call the same `generate_retail_invoice_s3_key(...)` and `upload_html_to_s3(...)` as Gmail, adding `'provider': 'outlook'` to the S3 object metadata dict.
- `process_user_sweep`, `process_single_user_backfill`, `process_all_users_sweep`, `lambda_handler` — same dual backfill/EventBridge dispatch pattern as Gmail's.
- Error handling: same shape, substituting `OutlookAPIError`/`RefreshTokenExpiredError` (502, new `ErrorCode.OUTLOOK_TOKEN_EXPIRED` in `responses.py`)/`OAuthValidationError` (401)/`SecretsManagerError` (502)/`UserNotFoundError` (404)/`DatabaseError` (500)/generic (500).

## Ledger table + classification pipeline — reuse unchanged

**What/why**: once an email's content is in hand, deciding "is this a retail invoice, and which category" is identical work regardless of which inbox it came from — so this logic is not duplicated, only tagged so you can tell Gmail- and Outlook-sourced invoices apart later if needed.

Same `RetailEmailClassificationLedger` table, same Jev→Gemini classification chain (text-based, already provider-agnostic). Add a minimal `provider` tag in two places only:
- Ledger entries written by `write_ledger_entry(...)` — add `provider="outlook"` (check its current signature; add as an optional kwarg defaulting to preserve Gmail call sites unchanged).
- S3 object metadata passed to `upload_html_to_s3(...)` — add `'provider': 'outlook'`.

No schema migration needed (DynamoDB/S3 metadata are schemaless).

## Terraform additions

**What/why**: wiring the two new Lambdas into AWS — giving each the permissions it needs (and only those), exposing the store-tokens Lambda as an API route the iOS app can call, and putting the sweep Lambda on a schedule so it runs without manual triggering.

- `aws-infra-terraform/lambdas/lambda_outlook_store_tokens.tf` — mirrors `lambda_gmail_store_tokens.tf` (timeout 15s, memory 128MB, layers `[utils_layer, pyjwt_layer]`, env `{JWT_SECRET, REGION, S3_BUCKET}`).
- `aws-infra-terraform/iam/iam_outlook_store_tokens_lambda.tf` — role `Outlook-Store-Tokens-Lambda-Role`, policy scoped to Secrets Manager on `outlook/user/*` plus S3 `PutObject` on `invoices/*` (new — needed since this path will actually run, unlike Gmail's dead one). Outlook client ID treated as a plain non-sensitive Terraform variable (`outlook_oauth_client_id`), not a Secrets Manager entry — it's a public app ID, simpler than Gmail's pattern.
- `aws-infra-terraform/api_gateway.tf` — new integration/route/permission trio for `POST /{api_version}/auth/outlook/store-tokens`, same pattern as Gmail's block.
- `aws-infra-terraform/lambdas/lambda_fetch_and_classify_outlook_invoices.tf` — mirrors the Gmail fetch Lambda's `.tf` (timeout 900s, memory 512MB), layers `[utils_layer, pyjwt_layer, jev_layer, google_genai_layer]` — drop `google_api_layer` (Google-API-client specific, not needed since Outlook uses plain `requests`). `requests` is confirmed NOT vendored in `utils_layer` today (no third-party packages are bundled there, and `lambda_layers/common` has no `requirements.txt`/build script at all, unlike `jev`/`gemini_parsers`/`google_genai` which each have one) — see new build-pipeline step below, this is required work, not an optional check.
  - Also add its own `aws_lambda_permission` resource (principal `events.amazonaws.com`, scoped `source_arn` to the EventBridge rule), mirroring `lambda_fetch_and_classify_retail_invoices.tf`'s existing permission resource. EventBridge invoking two different Lambdas off one rule needs a separate permission grant per target — without this, the new event target below will silently never invoke the Outlook Lambda (no error raised anywhere, it just never fires).
- `aws-infra-terraform/iam/iam_fetch_and_classify_outlook_invoices_lambda.tf` — mirrors the Gmail fetch Lambda's IAM file, substituting Secrets Manager scope to `outlook/user/*`; same Users/ledger table and S3 bucket/prefix grants (both providers write into the same `invoices/*/retail/*/*` structure).
- `aws-infra-terraform/eventbridge.tf`: add a second `aws_cloudwatch_event_target` ("OutlookInvoiceSweepTarget") under the existing `aws_cloudwatch_event_rule.retail_sweep_trigger`, pointing at `module.lambdas.fetch_and_classify_outlook_invoices_arn` — per decision, no new rule. Requires the matching `aws_lambda_permission` noted above or the target is a no-op.
- `lambda_layers/common/requirements.txt` (new) + a build script matching the `jev`/`gemini_parsers`/`google_genai` pattern (`build_layer.sh`, or `build_layer_docker.sh` if any vendored package needs architecture-specific binaries — `requests` itself is pure Python so plain `build_layer.sh` should suffice) — pip-installs `requests` into `utils_layer`'s `python/` dir before rezipping. This is new build infrastructure for this layer (none exists today), not a one-line addition to an existing file.

## Separate commit (before or alongside the Outlook work, but isolated): Gmail S3-folder-creation bugfix
- `lambdas/auth/gmail_store_tokens/main.py`: fix the call site that currently invokes an undefined `create_user_folder_in_s3` (singular) to call the real `create_user_folders_in_s3` (plural).
- `aws-infra-terraform/lambdas/lambda_gmail_store_tokens.tf`: add the missing `S3_BUCKET` env var so the (now-fixed) call path actually executes.
- Keep this as its own commit, isolated from any Outlook-feature commit, so it's independently reviewable/revertable.

## Build/test order

1. Create `lambda_layers/common/requirements.txt` (containing `requests`) and a build script for `utils_layer` matching the `jev`/`gemini_parsers`/`google_genai` pattern, then build and confirm `requests` lands in `utils_layer`'s `python/` dir — needed by every new Outlook function. No build pipeline exists for this layer today; this is new infrastructure, not a one-line check.
2. Before writing any Lambda code: check current Microsoft identity platform docs (Graph REST, MSAL public-client PKCE flow, refresh token rotation behavior) to confirm nothing below has changed since this plan was written.
3. Manually drive the auth-code+PKCE flow against `https://login.microsoftonline.com/common/oauth2/v2.0/authorize` (client ID `6861aa59-75ec-4dac-883e-0f9b96aa6576`, scopes `User.Read Mail.Read offline_access openid email`) via Postman/browser, exchange at `/token`, and sanity-check `GET /v1.0/me` and `GET /v1.0/me/messages?$top=5` with the resulting tokens before writing any Lambda code.

**Correction, confirmed live against a real consumer Microsoft account (2026-10-21)**: `GET /v1.0/me` requires the `User.Read` scope specifically — `Mail.Read` + `offline_access` alone are NOT sufficient and return `403 Forbidden` on `/v1.0/me` (mail endpoints like `/v1.0/me/messages` and `/v1.0/me/mailFolders` work fine with just `Mail.Read`). The original scope list above was missing `User.Read`. The iOS MSAL sign-in flow must request `User.Read Mail.Read offline_access` (plus `openid`/`email` for the ID token) or `get_outlook_user_info` will fail for every real user.
4. Implement `exceptions.py`, `oauth_utils.py`, and `secretsmanager_utils.py` additions — pure-function, unit-testable without AWS (mock `boto3.client` for the secrets functions). Test, then commit.
5. Implement `outlook_store_tokens` — test with a synthetic event carrying the real tokens from step 3; confirm secret `outlook/user/{test_user_id}` lands with the expected shape. Test, then commit.
6. Implement `outlook_api_utils.py` — specifically test the refresh path by forcing `expires_at` into the past and asserting `update_outlook_oauth_tokens` is called with Microsoft's *new* `refresh_token`, not the old one (direct regression test for the rotation-overwrite requirement). Test, then commit.
7. Implement `fetch_and_classify_outlook_invoices` — point at a real test Outlook inbox, invoke manually in `mode='backfill'` first (not cron), confirm S3 objects land under `invoices/{user_id}/retail/{category}/...` tagged `provider: outlook`. Test, then commit.
8. Confirm the existing S3-triggered `parse_retail_invoice` picks up these new objects with zero code changes — the key check that "downstream unchanged" actually holds.
9. Write the Terraform files above, run `terraform plan` (never `apply` without the user doing so), rebuild/reupload affected Lambda/layer zips to S3 first since Terraform won't detect source changes on its own. Test (plan output), then commit.
10. iOS client work (MSAL sign-in → POST to `/auth/outlook/store-tokens`) — last, once the backend contract is proven end-to-end.

At each step: if a question comes up (ambiguous existing behavior, a deprecated API surfaced by the docs check, an unexpected test result), pause and ask before proceeding — per Implementation rule 4.

## Critical files
- `lambdas/auth/gmail_store_tokens/main.py` — template for `outlook_store_tokens`
- `lambda_layers/common/python/utils/gmail_api_utils.py` — template for `outlook_api_utils.py`
- `lambda_layers/common/python/utils/secretsmanager_utils.py` — add `outlook_*` wrapper functions
- `lambda_layers/common/python/utils/oauth_utils.py` — add `get_outlook_user_info`, `validate_outlook_account_consistency`; verify `validate_oauth_tokens` is provider-agnostic
- `lambdas/invoices/fetch_and_classify_retail_invoices/lambda_function.py` — template for `fetch_and_classify_outlook_invoices`
- `aws-infra-terraform/lambdas/lambda_gmail_store_tokens.tf`, `aws-infra-terraform/iam/iam_gmail_store_tokens_lambda.tf` — Terraform templates
- `aws-infra-terraform/eventbridge.tf`, `aws-infra-terraform/variables.tf` — schedule wiring

