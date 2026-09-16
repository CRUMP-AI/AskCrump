# Autonomous Crump verification-policy candidate

Date: 2026-09-16

Parent source: `1015069440a06f426c5281a631deed0ec451ecd5`

Branch: `candidate/autonomous-verification-policy-20260916`

Status: local review candidate only; independently unaccepted, unpushed, undeployed, and disabled.

## Decision

Repository tests, build hooks, and check scripts are executable repository content. A coding model
must not be able to authorize that content merely by requesting a test command. Autonomous Crump
therefore prepares every task with one durable verification policy:

- `syntax_only` is the default. The model does not receive the project-check tool. After editing,
  the platform runs its own bounded Git integrity check and language syntax checks without executing
  repository tests or package scripts.
- `project_checks` is available only for an implementation task after the account holder explicitly
  selects it. The choice is stored with the prepared task and appears again in final run
  confirmation. Only then may the model request the existing bounded command grammar. Output remains
  length-bounded, credential-pattern-redacted, recorded for human review, and generated in the
  deny-all, credential-free, non-persistent workspace.
- Plan-only tasks cannot select or persist `project_checks` because they have no execution need.

This is permission to execute a narrow check inside the isolated copy, not permission to install
dependencies, access a network, read protected paths, publish, deploy, write to source control, or
skip human patch review.

## Defense in depth

- The browser sends the selected policy when the task is prepared; it cannot silently elevate a
  plan-only task.
- The server validates exactly `syntax_only` or `project_checks`, defaults closed, stores the choice
  in `code_tasks`, and returns it as a review fact. A database trigger rejects any later attempt to
  change that prepared-task authority, including through the service role.
- The model tool schema omits `run_verification` unless the stored task policy permits project
  checks.
- The runner independently rejects project-controlled executables unless its workspace was created
  from a task carrying the allowed policy.
- Even an allowed check is confined to the existing command grammar, deny-all networking, fixed safe
  environment, bounded runtime/output, secret-pattern redaction, and post-command workspace-integrity
  proof. A check that mutates an unauthorized path taints the run and blocks patch presentation.
- Built-in verification always records `git diff --check`; Python and JavaScript edits additionally
  receive bounded syntax checks without running project tests.

## Data boundary

The new migration adds only the content-free enum-like field `verification_policy` to the existing
owner-scoped task. It stores no prompt, source, test output, credential, URL parameter, or customer
content. Existing tasks inherit the closed `syntax_only` default.

## Validation and release boundary

Focused tests cover the closed default, explicit allow path, plan-only rejection, durable persistence,
tool-schema omission, runner enforcement, mutation tainting, UI review language, and the migration
constraint. Local validation passed the complete Python suite with one existing host-permission
skip, 54-file JavaScript source contract, 33/33 public accessibility matrix, desktop/phone
Autonomous Crump review fixture with no accessibility findings, offline 4/4 coding benchmark,
production preflight, native web-bundle construction, client-credential scan, Python lint and
compilation, JavaScript syntax, and Git diff integrity. The fail-closed browser-control matrix was
not rerun because shared fixture ports `4173`, `8765`, `8766`, `8767`, and `8770` were occupied by
other concurrent review work; no unrelated process was interrupted.

The exact committed revision still requires an independent review. This candidate changes no
feature switch and cannot make Autonomous Crump public. It must not be deployed or combined with
live activation evidence during the active acquisition-isolation window.
