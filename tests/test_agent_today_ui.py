"""Contract for the additive Agent Today layer on the app shell.

The layer is two new static files loaded last in app.html. It renders the
Today surface (approvals, live work, brief connect notice), the Tasks
drawer, and the browser panel shell from the agent endpoints, and it must
stay honest while those endpoints are still landing: no staged data, and
the browser panel states plainly that live sessions are not available yet.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def test_app_html_loads_agent_today_layer_last_with_versioned_assets():
    app = read('public/app.html')
    css = '/crump-agent-today-1.0.css?v=5.9.76-agent-today-14'
    js = '/crump-agent-today-1.0.js?v=5.9.76-agent-today-14'
    assert css in app
    assert js in app
    assert (PUBLIC / 'crump-agent-today-1.0.css').exists()
    assert (PUBLIC / 'crump-agent-today-1.0.js').exists()
    # Loaded last: after the vision shell and the auth controller, so the
    # layer can sit on top of the shell it extends.
    assert app.index(js) > app.index('/crump-vision-shell-1.0.js')
    assert app.index(js) > app.index('/auth-controller.js')
    assert app.index(css) > app.index('/crump-vision-shell-1.0.css')


def test_today_layer_reads_the_agent_contracts_with_the_owner_header():
    js = read('public/crump-agent-today-1.0.js')
    assert "'/api/agent/capabilities'" in js
    assert "'/api/agent/approvals'" in js
    assert "'/api/agent/runs'" in js
    assert '/decision' in js
    assert "decision: decision" in js
    assert "'X-Ask-Crump-Expected-Owner'" in js
    assert "credentials: 'include'" in js


def test_today_layer_renders_approvals_live_work_and_the_brief_notice():
    js = read('public/crump-agent-today-1.0.js')
    for needle in (
        'Waiting on you',
        'Live work',
        'Connect Google',
        'Built in Savannah',
        'browser.act',
        'Open browser',
        'Nothing needs you right now',
    ):
        assert needle in js, needle


def test_browser_panel_is_honest_about_execution_not_being_live():
    js = read('public/crump-agent-today-1.0.js')
    assert 'Per-user browser sessions are not live yet' in js
    assert 'pauseBtn.disabled = true' in js
    assert 'takeOverBtn.disabled = true' in js
    # No embedded browsing surface may be faked.
    assert 'iframe' not in js.lower()


def test_today_layer_declutters_without_removing_features():
    css = read('public/crump-agent-today-1.0.css')
    assert '[data-starter-prompt]' in css
    assert '.crump50-tool-chip' in css
    assert '#tutorialOverlay' in css


def test_today_layer_uses_the_house_palette_and_type():
    css = read('public/crump-agent-today-1.0.css')
    for needle in ('#070a0e', '#d5b971', '#b69855', '#f1efe9', '#8a9196', 'Georgia'):
        assert needle in css, needle
    assert 'min-height: 44px' in css


def css_block(css: str, selector: str) -> str:
    start = css.index(selector)
    open_brace = css.index('{', start)
    close_brace = css.index('}', open_brace)
    return css[open_brace:close_brace]


def test_today_surface_carries_its_own_ink_ground_and_off_white_greeting():
    css = read('public/crump-agent-today-1.0.css')
    # The greeting used to be ink text with no ground of its own, so on
    # the dark workspace ground it rendered ink-on-ink and read as
    # ghosted. The surface now carries the ink ground and the greeting
    # sits on it in off-white at full contrast in either theme.
    assert 'background: var(--cat-ink)' in css_block(css, '.cat-today {')
    assert 'color: var(--cat-paper)' in css_block(css, '.cat-today-title {')
    assert 'color: var(--cat-ink)' not in css_block(css, '.cat-today-title {')


def test_connect_prompt_is_a_slim_in_flow_notice_not_a_card():
    css = read('public/crump-agent-today-1.0.css')
    js = read('public/crump-agent-today-1.0.js')
    # The brief placeholder used to be a raised card in the brief area.
    # Review feedback removed the card entirely: the prompt is now a
    # plain in-flow notice — no panel fill, no border box, no positioned
    # overlay — with one short line of text and one small action.
    assert '.cat-connect {' not in css
    assert 'cat-card cat-connect' not in js
    assert 'Your brief is almost ready' not in js
    assert 'cat-connect-notice' in js
    notice = css_block(css, '.cat-connect-notice {')
    assert 'display: flex' in notice
    assert 'background' not in notice
    assert 'border' not in notice
    assert 'position' not in notice
    assert 'color: var(--cat-paper-dim)' in css_block(css, '.cat-connect-text {')
    button = css_block(css, '.cat-connect-btn {')
    assert 'color: var(--cat-gold-bright)' in button
    assert 'background: transparent' in button


def test_today_layer_owns_its_box_model_and_shrinks_in_the_workspace_grid():
    css = read('public/crump-agent-today-1.0.css')
    # Card geometry must not depend on the shell's global border-box
    # reset, and the Today grid item must be allowed to shrink so no
    # card body text clips at the right edge on narrow widths.
    assert '.cat-today *' in css
    assert 'box-sizing: border-box' in css
    grid_rule = css_block(
        css,
        'body.crump-v1-body .v1-workspace-body:has(> .cat-today:not([hidden])) > .cat-today {',
    )
    assert 'min-width: 0' in grid_rule


def test_today_reads_connection_status_and_brief_from_their_endpoints():
    js = read('public/crump-agent-today-1.0.js')
    # One source of truth for connection state: the status response
    # drives both the connect notice and brief availability, and the
    # brief renders from the brief endpoint's payload.
    assert "'/api/connections/google/status'" in js
    assert "'/api/agent/today'" in js
    assert 'googleConnected()' in js
    assert 'googleBriefIsPlanned' not in js


def test_waiting_section_shows_one_approval_with_a_counted_queue():
    js = read('public/crump-agent-today-1.0.js')
    # Only the first pending approval renders as the full card; the
    # rest sit behind one count row carrying the real remaining count
    # (approvals length minus one), and the row opens the Tasks panel,
    # where every pending approval renders in full.
    assert 'approvalCard(state.approvals[0])' in js
    assert 'state.approvals.length - 1' in js
    assert "' more waiting'" in js
    assert 'cat-queue-row' in js
    assert "queueRow.addEventListener('click', function () { openTasks(); })" in js
    assert 'cat-approval-queue-extra' not in js


def test_approval_card_leads_with_the_exact_action_and_collapsed_detail():
    js = read('public/crump-agent-today-1.0.js')
    # The card leads with the exact action derived from the frozen
    # payload (recipients, event, query), the payload itself sits
    # collapsed behind the detail toggle, and the credit line renders
    # ahead of the decision buttons.
    assert 'approvalExactSummary' in js
    assert 'payload.to' in js
    assert "'Open detail'" in js
    assert 'cat-approval-detail' in js
    assert js.index('cat-approval-detail') < js.index("button('Approve'")
    assert 'creditLine(action.capabilityId, action.creditCost)' in js


def test_live_work_shows_the_current_step_and_a_neutral_browser_tile():
    js = read('public/crump-agent-today-1.0.js')
    css = read('public/crump-agent-today-1.0.css')
    assert 'runStepText' in js
    assert 'Current step' in js
    assert 'cat-browser-tile' in js
    assert 'cat-browser-tile' in css
    # The tile falls back to chrome + step text, never a fake page.
    assert 'cat-browser-tile-text' in js


def test_brief_counts_and_rows_come_from_the_loaded_data():
    js = read('public/crump-agent-today-1.0.js')
    assert 'briefCountsText' in js
    assert 'inboxHighlights' in js
    assert 'cat-brief-card' in js
    assert 'cat-brief-row' in js


def test_today_cards_use_the_dark_card_token_with_gold_section_eyebrows():
    css = read('public/crump-agent-today-1.0.css')
    assert '.cat-today .cat-card {' in css
    assert 'background: #111417' in css
    section_title = css_block(css, '.cat-today-section-title {')
    assert 'color: var(--cat-gold-bright)' in section_title


def test_connect_button_hit_target_is_at_least_44px():
    css = read('public/crump-agent-today-1.0.css')
    button = css_block(css, '.cat-connect-btn {')
    assert 'min-height: 44px' in button


def test_chat_section_scopes_work_to_the_open_conversation():
    js = read('public/crump-agent-today-1.0.js')
    # The open conversation is the shell's own record: app.js keeps
    # window.currentChatId current and announces openings with the
    # crump:conversation-opened window event. Runs carry the same id
    # as conversationId; approvals join through their run.
    assert 'window.currentChatId' in js
    assert 'crump:conversation-opened' in js
    assert 'run.conversationId' in js
    assert 'action.runId' in js
    assert 'catChatWork' in js
    assert 'chatIsActive' in js
    # The section is a sibling after the message list, never a write
    # into the shell's message DOM.
    assert "getElementById('chatContainer')" in js
    assert 'container.nextSibling' in js


def test_chat_cards_reuse_the_shared_builders_exactly_once():
    js = read('public/crump-agent-today-1.0.js')
    # The Chat surface renders with the same approval/run builders as
    # Today and Tasks — the exact-action rule is inherited, not forked.
    assert js.count('function approvalCard(') == 1
    assert js.count('function runCard(') == 1
    assert 'approvalCard(primary.action)' in js
    assert 'runCard(primary.run)' in js
    assert 'approvalExactSummary(item.action)' in js


def test_chat_surface_has_one_primary_card_and_quiet_secondary_rows():
    js = read('public/crump-agent-today-1.0.js')
    css = read('public/crump-agent-today-1.0.css')
    assert 'cat-chat-primary' in js
    assert 'cat-chat-row' in js
    assert 'chatSecondaryRow' in js
    assert '.cat-chat-work .cat-card {' in css
    assert 'background: #111417' in css
    # A secondary approval row routes to the full card in Tasks.
    assert "row.addEventListener('click', function () { openTasks(); });" in js


def test_chat_section_renders_nothing_without_work_or_for_guests():
    js = read('public/crump-agent-today-1.0.js')
    # No work in the open conversation: the section hides and clears —
    # no empty placeholder, no instructional copy in the chat render.
    assert 'if (!active || !items.length)' in js
    assert 'node.hidden = true' in js
    # The guest gate is the same owner check that gates the fetches.
    assert 'captureOwnerId() && state.loaded' in js


def test_chat_section_never_renders_on_the_today_home_state():
    js = read('public/crump-agent-today-1.0.js')
    # v1-home is the launchpad/Today state; the chat gate rejects it.
    assert "document.body.classList.contains('v1-home')" in js


def test_composer_bar_is_plus_input_and_send_only():
    app = read('public/app.html')
    container = app[app.index('class="input-container"'):app.index('</section>', app.index('class="input-container"'))]
    # The visible composer bar carries exactly the attach ("+") control,
    # the text input, and send — in that order. Everything else the
    # attach affordance opens lives behind it, in its own sheet.
    assert container.index('id="attachBtn"') < container.index('id="userInput"') < container.index('id="sendButton"')
    assert container.count('<button') == 2
    assert container.count('<textarea') == 1


def test_tasks_loads_automations_inside_the_same_auth_gated_feed():
    js = read('public/crump-agent-today-1.0.js')
    # Automations join the one auth-gated load: the fetch sits in the
    # same Promise.all behind captureOwnerId, so guests gain no new
    # calls and signed-out sessions fetch nothing at all.
    assert "settled(api('/api/agent/automations'))" in js
    assert 'state.automations' in js
    load = js[js.index('function loadAgentData()'):js.index('function liveRuns()')]
    assert "if (!captureOwnerId())" in load
    assert load.index("if (!captureOwnerId())") < load.index("'/api/agent/automations'")


def test_tasks_groups_render_in_the_locked_record_order():
    js = read('public/crump-agent-today-1.0.js')
    render = js[js.index('function renderTasks()'):]
    assert render.index("'Waiting on you'") < render.index("'Running'")
    assert render.index("'Running'") < render.index("'Scheduled'")
    assert render.index("'Scheduled'") < render.index("'Done'")
    assert 'Nothing is scheduled.' in js


def test_scheduled_rows_derive_their_line_from_stored_fields_only():
    js = read('public/crump-agent-today-1.0.js')
    # The schedule line reads the record's own schedule kind/time and
    # its stored next run. No frequency wording is invented: the only
    # daily phrasing is keyed to the stored daily kind.
    assert 'automationScheduleLine' in js
    assert 'schedule.kind' in js
    assert 'fmtScheduleTime(schedule.time)' in js
    assert 'automation.nextRunAt' in js
    assert "'Daily at '" in js
    assert 'every weekday' not in js.lower()
    assert 'automation.lastRunAt' in js


def test_paused_automations_stay_in_the_scheduled_group():
    js = read('public/crump-agent-today-1.0.js')
    # Paused automations are part of the standing record: the group
    # renders every loaded automation, enabled or not, with its real
    # status, instead of filtering paused rows out or filing them
    # under Done.
    assert 'state.automations.forEach' in js
    assert 'automationRow(automation)' in js
    assert "'Scheduled' : 'Paused'" in js
    assert 'automation.enabled' in js


def test_tasks_waiting_group_keeps_every_approval_as_a_full_card():
    js = read('public/crump-agent-today-1.0.js')
    # The Today queue row routes here for the rest of the approvals:
    # the Waiting group renders the full shared approval card for each
    # pending action, never a demoted row.
    render = js[js.index('function renderTasks()'):js.index('function renderTasks()') + 2600]
    assert 'waitingGroup.appendChild(approvalCard(action))' in render
    assert js.count('function approvalCard(') == 1


def test_tasks_drawer_uses_the_dark_record_treatment():
    css = read('public/crump-agent-today-1.0.css')
    # The drawer is a dark surface in the design: ink ground, gold
    # tracked group eyebrows, flat rows separated by gold hairlines,
    # and the dark card token scoped to cards inside the drawer.
    assert 'background: var(--cat-ink)' in css_block(css, '.cat-drawer {')
    assert 'color: var(--cat-gold-bright)' in css_block(css, '.cat-group-title {')
    assert '.cat-drawer .cat-card {' in css
    row = css_block(css, '.cat-task-row {')
    assert 'background: transparent' in row
    assert 'rgba(213, 185, 113' in row
    assert '.cat-row-marker' in css


def test_chat_work_row_is_capped_so_the_message_row_cannot_collapse():
    css = read('public/crump-agent-today-1.0.css')
    # The section row used to be sized by the section's own content
    # (minmax(0, auto)): a tall approval card claimed the whole
    # workspace body, the message row collapsed to zero height, and
    # the message list's box overflowed that row and painted over the
    # section. The row is now capped at a share of the body height so
    # both surfaces always hold real height and scroll in their rows.
    grid_rule = css_block(
        css,
        'body.crump-v1-body .v1-workspace-body:has(> .cat-chat-work:not([hidden])) {',
    )
    assert 'grid-template-rows: minmax(0, 1fr) minmax(0, 60%)' in grid_rule
    assert 'minmax(0, auto)' not in grid_rule


def test_card_header_stacks_at_narrow_widths():
    css = read('public/crump-agent-today-1.0.css')
    # At phone widths the badge used to squeeze into the space beside
    # the headline. Under the narrow breakpoint the header stacks, so
    # the badge takes its own line and the headline keeps the full
    # card content width; the desktop row arrangement is unchanged.
    narrow = css[css.index('@media (max-width: 480px)'):]
    narrow = narrow[:narrow.index('@media', 1)]
    assert '.cat-card-head' in narrow
    assert 'flex-direction: column' in narrow
    assert '.cat-card-head .cat-status' in narrow
    head = css_block(css, '.cat-card-head {')
    assert 'display: flex' in head
    assert 'flex-direction' not in head


def test_secondary_summary_line_renders_only_complete_sentences():
    js = read('public/crump-agent-today-1.0.js')
    # Stored summaries and capability verb phrases are headline
    # fragments ("Send an email — Send an email to", "Open the
    # browser and"). Both card builders gate the secondary line on
    # the shared completeness rule; a fragment never renders.
    assert 'summaryAddsInformation' in js
    assert 'DANGLING_FINAL_WORDS' in js
    assert 'summaryAddsInformation(action.summary, exact)' in js
    assert 'summaryAddsInformation(cap.verbPhrase, capabilityTitle(run.capabilityId))' in js


def test_frozen_detail_renders_payload_values_exactly():
    js = read('public/crump-agent-today-1.0.js')
    # The detail behind the toggle is the inspectable frozen payload:
    # array fields list every item and no field is reduced to a
    # count or silently truncated.
    payload_list = js[js.index('function payloadList(payload)'):]
    payload_list = payload_list[:payload_list.index('function creditLine')]
    assert "' items'" not in payload_list
    assert "'1 item'" not in payload_list
    assert '220' not in payload_list
    assert "join('\\n')" in payload_list


def test_nav_relabels_home_and_adds_tasks_without_touching_the_shell():
    js = read('public/crump-agent-today-1.0.js')
    assert 'data-cv-destination' in js
    assert 'data-cat-tasks' in js
    assert "'Today'" in js or '"Today"' in js or "'Today'" in js
    shell = read('public/crump-vision-shell-1.0.js')
    assert 'crump-agent-today' not in shell


def test_browser_panel_is_a_right_anchored_slide_over_with_gold_hairline():
    css = read('public/crump-agent-today-1.0.css')
    window = css[css.index('.cat-browser-window {'):css.index('@keyframes cat-browser-in')]
    # Slide-over geometry: ~84% of the viewport on phone widths,
    # capped at a wide side panel on desktop, full height, anchored
    # to the right edge over a dimming backdrop.
    assert 'width: min(560px, 84vw)' in window
    assert 'height: 100%' in window
    assert 'background: #111417' in window
    assert 'border-left: 1px solid rgba(213, 185, 113, 0.35)' in window
    backdrop = css[css.index('.cat-browser {'):css.index('.cat-browser[hidden]')]
    assert 'justify-content: flex-end' in backdrop
    assert 'background: rgba(7, 10, 14, 0.48)' in backdrop
    # The old centered-modal and full-screen phone shapes are gone.
    assert 'width: min(880px, 100%)' not in css
    # Entry motion exists and respects reduced motion.
    assert '@keyframes cat-browser-in' in css
    reduced = css[css.index('@media (prefers-reduced-motion: reduce)'):]
    assert '.cat-browser-window' in reduced


def test_browser_panel_step_is_one_line_and_controls_stay_distinct_and_honest():
    js = read('public/crump-agent-today-1.0.js')
    css = read('public/crump-agent-today-1.0.css')
    # The header carries the title and the one-line current step.
    assert "'Live browser'" in js
    assert 'aria-labelledby' in js and 'catBrowserTitle' in js
    step = css[css.index('.cat-browser-step {'):css.index('.cat-browser-head-actions')]
    assert 'white-space: nowrap' in step
    assert 'text-overflow: ellipsis' in step
    # Pause and dismissal are separate elements: Pause stays an
    # honest disabled control while sessions are not live, and Back
    # is the enabled dismiss affordance, labelled as dismissal.
    assert "button('Pause', 'cat-btn cat-browser-pause')" in js
    assert "button('Back', 'cat-icon-btn cat-browser-dismiss', closeBrowserPanel)" in js
    assert 'Back — close the browser panel' in js
    panel = js[js.index('function ensureBrowserPanel()'):js.index('function openBrowserPanel(run)')]
    assert panel.count('disabled = true') == 2  # Pause + Take over
    # A rightward swipe dismisses; nothing fakes a live session.
    assert "addEventListener('touchend'" in js
    assert 'Per-user browser sessions are not live yet' in js


def test_browser_panel_contains_keyboard_focus_while_open():
    js = read('public/crump-agent-today-1.0.js')
    # The panel is modal: the document keydown listener routes Tab
    # to the containment helper whenever the panel is open, so focus
    # cycles inside the panel instead of walking out into the
    # dimmed chat behind it.
    assert "event.key === 'Tab' && browserPanel && !browserPanel.hidden" in js
    assert 'keepBrowserPanelFocus(event)' in js
    # The focusable set skips disabled controls — Pause and Take
    # over while sessions are not live — so with Back as the only
    # enabled control, both directions land back on Back.
    helper = js[js.index('function browserPanelFocusables()'):js.index('function keepBrowserPanelFocus')]
    assert 'node.disabled' in helper
    trap = js[js.index('function keepBrowserPanelFocus(event)'):js.index('Navigation: Home becomes Today')]
    assert 'browserPanel.contains(active)' in trap
    assert 'event.shiftKey' in trap
    assert 'focusables[0]' in trap
    assert 'focusables[focusables.length - 1]' in trap


def test_surfaces_own_the_ground_without_a_sheet():
    css = read('public/crump-agent-today-1.0.css')
    # Today and the Chat work section paint the ink edge-to-edge: no
    # width cap, no inset margin, no border, no radius on the surface
    # containers. Cards keep their own borders and radius; only the
    # surface-level sheet is gone.
    for selector in ('\n.cat-today {', '\n.cat-chat-work {'):
        block = css_block(css, selector)
        assert 'background: var(--cat-ink)' in block
        assert 'margin: 0' in block
        assert 'max-width' not in block
        assert 'border' not in block
    # No inset survives in the small-screen overrides either.
    assert 'calc(100% - 16px)' not in css
    assert 'max-width: 880px' not in css
    # The hosting workspace body takes the same ink while a surface
    # is up in the dark appearance, so no second, different black
    # shows around it. The rule is dark-scoped: in the light
    # appearance the shell's hero and message text are dark on light
    # by design, and forcing the container to ink breaks their
    # contrast pairing.
    ground = css_block(
        css,
        'html[data-theme="dark"] body.crump-v1-body .v1-workspace-body:has(> .cat-today:not([hidden])),',
    )
    assert 'background: var(--cat-ink) !important' in ground


def test_spacing_tokens_match_the_design_scale():
    css = read('public/crump-agent-today-1.0.css')
    root = css_block(css, ':root {')
    assert '--cat-radius: 24px' in root
    assert '--cat-section-gap: 44px' in root
    assert '--cat-card-padding: 28px' in root
    assert '--cat-stack-gap: 28px' in root
    assert 'margin-top: var(--cat-section-gap)' in css_block(css, '.cat-today-section {')
    card = css_block(css, '.cat-card {')
    assert 'padding: var(--cat-card-padding)' in card
    assert 'border-radius: var(--cat-radius)' in card
    assert 'gap: var(--cat-stack-gap)' in css_block(css, '.cat-today-stack {')
    assert 'gap: var(--cat-stack-gap)' in css_block(css, '.cat-chat-stack {')


def test_greeting_is_hero_scale_serif_and_card_titles_are_inter():
    css = read('public/crump-agent-today-1.0.css')
    # The greeting is the hero: Georgia at a vw-driven hero scale.
    title = css_block(css, '.cat-today-title {')
    assert 'Georgia' in title
    assert 'clamp(50px, 13.5vw, 76px)' in title
    # Card titles are Inter bold; serif is reserved for the greeting,
    # page titles, the brief title, and project names.
    card_title = css_block(css, '.cat-card-title {')
    assert 'Inter' in card_title
    assert 'Georgia' not in card_title
    assert 'font-size: 21px' in card_title
    assert 'font-weight: 700' in card_title
    assert 'Georgia' in css_block(css, '.cat-brief-title {')
    assert 'Georgia' in css_block(css, '.cat-drawer-title {')


def test_eyebrow_pairs_the_monogram_chip_with_the_text():
    css = read('public/crump-agent-today-1.0.css')
    js = read('public/crump-agent-today-1.0.js')
    # The eyebrow is the gold C chip beside the tracked text, drawn
    # in CSS — no brand asset file is touched.
    chip = css_block(css, '.cat-eyebrow-chip {')
    assert 'border: 1px solid rgba(213, 185, 113' in chip
    assert 'border-radius: 9px' in chip
    assert 'Georgia' in chip
    assert 'cat-eyebrow-chip' in js
    eyebrow = css_block(css, '.cat-today-eyebrow {')
    assert 'display: flex' in eyebrow


def test_greeting_sets_on_two_lines():
    js = read('public/crump-agent-today-1.0.js')
    # The daypart and the name render on separate lines (the design's
    # two-line greeting) while the headline string itself is unchanged.
    assert "headline.indexOf(', ')" in js
    assert "document.createElement('br')" in js
    assert 'greetingHeadline()' in js
