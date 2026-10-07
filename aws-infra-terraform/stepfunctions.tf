# Step Functions state machine for orchestrating historical retail invoice backfill.
#
# Fans a pre-computed list of bounded (start_date, end_date] batch windows out to
# fetch_and_classify_retail_invoices, running up to MaxConcurrency batches at once.
# Deliberately dumb/generic - no date-chunking logic lives here, the caller (today:
# scripts/start_historical_retail_backfill.py; later: an app-triggered API route)
# computes the batch list and passes it as execution input:
#
#   {
#     "user_id": "...",
#     "batches": [
#       {"start_date": "2020-01-01", "end_date": "2020-04-01", "max_pages": 15},
#       ...
#     ]
#   }
#
# No Jobs table needed - RetailEmailClassificationLedger already tracks per-message
# progress, batches don't overlap by construction, and Step Functions' own execution
# history provides per-batch status/observability for free.

resource "aws_iam_role" "retail_backfill_sfn_role" {
  name = "Retail-Invoice-Backfill-StepFunctions-Role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "states.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "retail_backfill_sfn_policy" {
  name = "Retail-Invoice-Backfill-StepFunctions-Policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = ["lambda:InvokeFunction"],
        Resource = module.lambdas.fetch_and_classify_retail_invoices_arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "retail_backfill_sfn_policy_attachment" {
  role       = aws_iam_role.retail_backfill_sfn_role.name
  policy_arn = aws_iam_policy.retail_backfill_sfn_policy.arn
}

resource "aws_sfn_state_machine" "retail_invoice_backfill" {
  name     = "retail-invoice-backfill"
  role_arn = aws_iam_role.retail_backfill_sfn_role.arn

  definition = jsonencode({
    Comment = "Fans out bounded historical backfill batches to fetch_and_classify_retail_invoices"
    StartAt = "RunBatches"
    States = {
      RunBatches = {
        Type           = "Map"
        ItemsPath      = "$.batches"
        MaxConcurrency = 4
        # Isolates one batch's failure from the rest: without this, a single failed
        # iteration (e.g. a dense quarter that hits the Lambda's 900s timeout) aborts
        # every other concurrently-running batch and fails the whole execution, even
        # though those siblings were succeeding fine on their own. 25% of 28 batches is
        # 7 - generous enough to absorb a handful of genuinely oversized historical
        # quarters without masking a real systemic problem (e.g. a bad user_id) that
        # would fail most/all batches.
        ToleratedFailurePercentage = 25
        # Within ItemSelector, "$" is the Map state's own raw input (the whole
        # {user_id, batches} object) - NOT the current item. The current item must be
        # reached via the context object, $$.Map.Item.Value. This merges user_id (from
        # $$.Execution.Input) with the current batch's fields into one flat object, so
        # the Task below can reference everything as a plain "$.field".
        ItemSelector = {
          "user_id.$"    = "$$.Execution.Input.user_id"
          "start_date.$" = "$$.Map.Item.Value.start_date"
          "end_date.$"   = "$$.Map.Item.Value.end_date"
          "max_pages.$"  = "$$.Map.Item.Value.max_pages"
        }
        Iterator = {
          StartAt = "InvokeBackfillBatch"
          States = {
            InvokeBackfillBatch = {
              Type     = "Task"
              Resource = "arn:aws:states:::lambda:invoke"
              Parameters = {
                FunctionName = module.lambdas.fetch_and_classify_retail_invoices_arn
                Payload = {
                  "mode"         = "backfill"
                  "user_id.$"    = "$.user_id"
                  "start_date.$" = "$.start_date"
                  "end_date.$"   = "$.end_date"
                  "max_pages.$"  = "$.max_pages"
                }
              }
              # This Retry only covers the AWS-level Lambda invoke call failing
              # (throttling/service errors) - it has no visibility into the Lambda's own
              # response body, which is why CheckBatchResult below exists.
              Retry = [
                {
                  ErrorEquals     = ["Lambda.TooManyRequestsException", "Lambda.ServiceException"]
                  IntervalSeconds = 10
                  MaxAttempts     = 3
                  BackoffRate     = 2.0
                },
                {
                  # A timed-out batch already wrote every message it got through to the
                  # ledger before being killed, so retrying isn't wasted work - the next
                  # attempt skips everything already classified and only processes what's
                  # left, converging on completion within a few attempts for a dense
                  # quarter. Separate (longer) backoff since each attempt can itself take
                  # up to 900s - this is not a quick transient error.
                  ErrorEquals     = ["Sandbox.Timedout"]
                  IntervalSeconds = 30
                  MaxAttempts     = 2
                  BackoffRate     = 1.0
                }
              ]
              Next = "CheckBatchResult"
            }
            # The lambda:invoke integration only fails this Task on an AWS-level
            # invocation error (throttling, service exception, etc.) - it has no idea
            # whether the Lambda's own returned payload represents success or an
            # application-level error (e.g. a 404 for an unresolvable user_id, or a 400
            # for a malformed/oversized backfill request). Without this check, a batch
            # that silently failed inside the Lambda still reports as a Map iteration
            # success, and the whole execution misleadingly shows SUCCEEDED despite doing
            # zero real work - exactly what happened when a malformed user_id was passed.
            CheckBatchResult = {
              Type = "Choice"
              Choices = [
                {
                  Variable              = "$.Payload.statusCode"
                  NumericGreaterThanEquals = 400
                  Next                  = "BatchFailed"
                }
              ]
              Default = "BatchSucceeded"
            }
            BatchFailed = {
              Type  = "Fail"
              Error = "BackfillBatchFailed"
              Cause = "fetch_and_classify_retail_invoices returned an error status code for this batch - check the Task output's Payload.body, or CloudWatch Logs for /aws/lambda/fetch_and_classify_retail_invoices, for details"
            }
            BatchSucceeded = {
              Type = "Pass"
              End  = true
            }
          }
        }
        End = true
      }
    }
  })
}
