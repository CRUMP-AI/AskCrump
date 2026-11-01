# Code Studio — Integration Spec
*Absorbing the Crump Code agent engine as a first-class Ask Crump feature. 2026-10-03.*

## 1. What it is

The standalone coding-agent app is absorbed; its engine becomes **Code Studio**, a creation surface inside Ask Crump alongside Image Studio, Video Studio, and Canvas. One workspace, one login, one subscription. Chat, Projects, Library — and now code.

The core insight: code without context is just files. Inside Ask Crump, code inherits the project's memory — its conversations, documents, prior decisions — which is what makes the agent feel smart instead of mechanical.

## 2. Where it surfaces

| Surface | Placement | Reasoning |
|---|---|---|
| Sidebar nav | Under **Create**, after Canvas | Studios are creation surfaces; code is creation. It belongs with its siblings, not buried in settings. |
| Phone tab bar | 6th tab ("Code") | First-class means thumb-reachable. Six small tabs fit at 392pt. |
| Composer "+" sheet / FAB Create sheet | "Write code" entry | Meets users at the moment of intent, next to "New image" / "New document". |
| Project detail | "Open in Code Studio" button | Code is a project citizen. A portfolio project *has* code the way it has chats and files. |
| Chat | Natural handoff | "Build me a portfolio site" in chat opens Code Studio with the conversation as context. No re-explaining. |

## 3. How it shares context

- **Code lives in the project.** Code files are project files — same storage as documents and images, visible in project file lists, backed up with the project.
- **The agent reads the project.** "Fix the typo on my about page" works because the project knows there *is* an about page, what it says, and what was discussed about it.
- **Canvas synergy.** A project's README or docs render in Canvas; code and prose stay linked.
- **Library.** A finished code project is a keepsake like any other — save it, reopen it, share it.

## 4. The core loop

**Describe → Write → Preview → Run → Diff → Checkpoint.**

1. User describes what they want in plain words (or picks a starter idea).
2. Crump writes the code visibly in the editor — never a black box.
3. **Preview** renders instantly (HTML/CSS/JS) or **Run** executes (Python) with an output console.
4. Every AI change arrives as a **diff**: before/after lines plus a plain-language summary ("I made the hero headline bigger and centered it"). Accept or Discard.
5. Every accepted change auto-creates a **checkpoint**. A timeline lists them; one tap restores any version.

**Approvals:** destructive or surprising actions (delete a file, run shell, install a package) ask first, in plain language. Never a terminal dump, never silent mutation.

## 5. v1 scope: start narrow

- **Languages:** HTML/CSS/JS (where preview *is* the product) + Python (console run). The loop matters more than language count; breadth comes later.
- **Runtimes:** in-browser sandboxed iframe for web; ephemeral server sandbox for Python (CPU/memory/time limits, no network, no persistence except files explicitly saved to the project).
- **Not in v1:** shell access, package installs, repo cloning, multi-file refactors across languages.

## 6. Sandboxing posture

- **Frontend:** sandboxed iframes with no same-origin access to the app. Preview code can never touch user data.
- **Python:** ephemeral container per run. Timeouts kill runaways. No network. The agent's file tools are scoped to the project directory — path escapes refused, never touched.
- **Secrets:** the agent never sees user credentials. API keys for user code go through project environment settings, never pasted into chat.

## 7. Friendly to non-coders (the Greg directive)

- **The editor is a window, not a requirement.** A user can live entirely in describe → preview → accept and never touch code. The code is there when curiosity strikes, invisible when it doesn't.
- **Everything is explained in plain words**, before and after. Diff summaries are human sentences, not patch syntax.
- **"Nothing breaks here. Every change can be undone."** Checkpoints are the safety net that makes experimenting feel safe — the single most important friendliness feature.
- **Starter ideas, not blank editors.** Progressive disclosure everywhere: details on demand, never up front.

## 8. Non-goals (v1)

- Not a full IDE: no vim bindings, no multi-cursor, no extensions marketplace.
- Not a deployment platform: preview/share links only, no "deploy to production".
- Not a repo manager: no git clone/push in v1; import/export as zip instead.
- Not a second app, second login, or second subscription. One Ask Crump.
- Not a terminal replacement: no raw shell for users in v1, period.

## 9. Name

The directive calls the feature "Code Studio", which also matches the Studio family (Image / Video / Document). Ranked proposals with reasoning go in the delivery report — the name call is Greg's.
