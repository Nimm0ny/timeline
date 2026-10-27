# Chronicle notebook and Agent program

P00 through P05 first deliver a lightweight, usable, high-performance Web notebook.
Markdown is the default format. The human note workflow, typed FastAPI contract, generated Web types, Feature Map, and named CLI operations reach a complete state before Agent runtime work begins.
JSON and `.xlsx` use the same document identity and API model through format adapters.
P06 adds proactive Agent collaboration on top of the finished notebook, API, CLI, and format contracts.
Chronicle owns document identity, revisions, Agent policies, task state, permissions, progress, and reviewable changes.
The Web release must pass real UI, API, CLI, accessibility, recovery, resource, and performance checks.
Desktop work starts only after the Web exit gate passes.

## How to read this

One box is one unit of work. Every box names the evidence that checks it. A nested box is a sub-step of the box above it. Check a box only when its evidence exists, such as a file, a log line, a screenshot, a test run, or a SHA. The body is a how-to. The appendices explain the decisions and the current baseline.

The program runs `vendor/pstack/skills/poteto-mode/playbooks/autopilot-stack.md`. P00 through P07 form one base-chained Web stack. P00 through P05 complete the notebook product before P06 adds Agent runtime behavior. The operator reviews and lands the stack bottom-up. P08 is a separate follow-up after the Web gate.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

The P00 through P08 labels are planning IDs, not GitHub PR numbers. Do not create branches or PRs during this planning pass.

## Program checklist

### Arm the program

- [ ] Re-read the current source, `AGENTS.md`, and this plan before each phase. Resolve a clean base from the local `main`, `origin/main`, and current changes before creating a worktree.
- [ ] Capture the current source SHA, all uncommitted changes, deleted files, and untracked files. Do not reset or overwrite the working tree to create the clean base.
- [ ] Record current API routes, Feature Map entries, CLI commands, browser tasks, test commands, asset sizes, memory use, storage growth, and performance measurements in the P00 baseline receipt.
- [ ] Use the existing local prototype evidence in Appendix A only for the co-writing interaction. Prototype the note home and format choice for P00. Prototype the future proactive Agent rule and inbox as design evidence only; do not build Agent runtime before P06.
- [ ] Resolve the hosting and canonical storage gates before P02. Resolve the `.xlsx` scope before P05. Resolve the Agent runtime, background availability, provider, and budget gates before P06.
- [ ] Keep P00 through P05 focused on the human notebook, its complete API contract, its CLI, format adapters, and lightweight operation. Do not add Agent-triggered writes during these phases.
- [ ] Run `node vendor/pstack/skills/poteto-mode/scripts/check-plan.mjs docs/plan/chronicle-agent-era-program.md` after plan edits and keep its output with the plan review.
- [ ] After the operator's execution go, arm the audit tick as `/loop 1h`. The tick records a row and posts a status message only when tracked program state changes. Do not arm a loop for this planning pass.
- [ ] Before each unit, read the selected playbook from the current trunk with `git show origin/main:vendor/pstack/skills/poteto-mode/playbooks/autopilot-stack.md`. If `origin/main` no longer names trunk, record and use the verified trunk ref.

### Spawn owners

- [ ] Assign one writer to each P00 through P07 unit. Give each writer an isolated worktree and only the paths listed in that unit.
- [ ] Keep P00 through P07 base-chained in dependency order. Start a unit only after its parent is verified and its API and Feature Map changes are available.
- [ ] Give each unit a verifier who checks the real Web and CLI behavior against its receipts. Follow the repository's review rule before starting any separate code review.
- [ ] Keep P08 parked until the P07 Web exit gate passes and the operator starts the desktop follow-up.

### PR mechanics

- [ ] Resolve the current base and remote before creating the stack. The planning pass performs no fetch, push, PR creation, merge, release, or deployment.
- [ ] Open implementation PRs ready for review, base each PR on its planned parent, and stop at STACK-READY for the operator to land the stack.
- [ ] Run the relevant test, type, browser, CLI, and performance checks for each unit before its code-ready report.
- [ ] Keep every unit's screenshots, videos, JSON receipts, and benchmark output under `artifacts/pstack/<unit-id>/` in its isolated checkout. Do not write test data to `data/timeline.db`.
- [ ] Update the one authoritative API schema, Feature Map, Web operation, CLI operation, and runnable scenario together. Do not add a temporary second API or compatibility implementation.

### Verdict and merge

- [ ] Verify every current PR head against its unit, live, and perf boxes. A new head invalidates the prior verdict.
- [ ] Review all ten live lanes and the benchmark receipt before marking a unit STACK-READY.
- [ ] Hold every interaction-changing PR at the operator review gate with its screenshots and 30 to 60 second video.
- [ ] Land only the contiguous verified stack in dependency order. Keep old databases and attachments untouched.

### Boot recipe

Each live lane starts a disposable Chronicle test service with an isolated data directory. Use the repo-owned browser runner for Web lanes and the CLI process runner for CLI lanes.

- [ ] Create a fresh test workspace and database from the selected test configuration.
- [ ] Start the backend and Web client through the owned test runner. Wait for both health checks.
- [ ] Use browser controls for Web actions and the named Chronicle CLI command for Agent actions. Do not call SQL or unregistered routes from a test lane.
- [ ] Record the exact command, API operation IDs, document IDs, revisions, and test data in the JSON receipt.
- [ ] Capture `artifacts/pstack/<unit-id>/lane-<nn>.png` for each lane. Capture the review video only for a user-visible interaction change.
- [ ] Stop only the process owned by the test runner and remove only the disposable workspace it created.

## Establish the baseline and prototype the product (P00)

**Depends on.** None. This unit starts after the operator approves a clean source base.

**Files.**

- [ ] Add the baseline and prototype record under `docs/plan/`.
- [ ] Add an isolated application test configuration under `backend/app/core/`.
- [ ] Add the fixed CLI verification runner under `tools/chronicle_cli.py` and `tools/qa/`.
- [ ] Add a browser behavior test command and its owned fixtures under `package.json` and `ui/tests/`.
- [ ] Add repeatable API and Web measurements under `tools/bench/`.

**Build.**

- [ ] Capture the current routes, schemas, UI flows, CLI commands, and test coverage on the chosen baseline.
- [ ] Keep the dev runner responsible only for application processes that it starts. Let repository test tooling own test processes.
- [ ] Keep test-suite selection and coverage reporting outside the application CLI.
- [ ] Prototype a human-first note home and a format-aware document open flow. Add a separate proactive Agent rule and inbox prototype for the later P06 review.
- [ ] Compare the P00 note and format prototypes against the existing co-writing evidence. Record the selected human workflow and keep Agent behavior as a later implementation gate.
- [ ] Capture cold and warm p50 and p95 for note listing, note open, search, save acknowledgement, and CLI startup on 1,000 and 10,000 document fixtures.
- [ ] Record browser asset bytes, first interactive state, browser and backend idle and peak memory, backend idle CPU, and database and attachment growth for the same fixtures.
- [ ] Propose absolute budgets for asset size, latency, memory, idle CPU, storage growth, and attachment processing from the measured baseline. Get operator approval with the P00 prototype review.

**You see.**

- [ ] The dev runner prints one JSON result on stdout, sends progress to stderr, and identifies its isolated data path.
- [ ] A failed test run names the failed lane, stable error code, and a next action.
- [ ] The note prototype opens and edits Markdown without Agent setup. The separate Agent prototype shows a persistent rule that can create a proposal without a per-task prompt.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Run `python -m pytest -q` against the isolated test database. Confirm that test startup does not import, migrate, or write `data/timeline.db`.
- [ ] Run `npm run test:ui` and `npm run build`. Confirm that browser tests use the disposable backend.
- [ ] Run `python tools/generate_api_types.py --check`. Confirm repository test tooling reports any missing suite instead of passing silently.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.7-xhigh-fast` at the PR head, per the boot recipe.

- [ ] Lane 1. Start the test service with an empty workspace. Save `artifacts/pstack/P00/lane-01.png`. Pass when the Web and CLI both report the same workspace identity.
- [ ] Lane 2. Run `python tools/chronicle_cli.py feature list` against the test service. Save `artifacts/pstack/P00/lane-02.png`. Pass when stdout parses as one Feature Map JSON value.
- [ ] Lane 3. Run `chronicle doctor` with a missing API route in the fixture. Save `artifacts/pstack/P00/lane-03.png`. Pass when it names the missing operation and exits nonzero.
- [ ] Lane 4. Run a test that creates a note through the Web API. Save `artifacts/pstack/P00/lane-04.png`. Pass when the returned note can be read back through CLI HTTP.
- [ ] Lane 5. Run the same test with an invalid request field. Save `artifacts/pstack/P00/lane-05.png`. Pass when the API and CLI return the same error code and field path.
- [ ] Lane 6. Run `python tools/chronicle_cli.py dev doctor` with a stopped service. Save `artifacts/pstack/P00/lane-06.png`. Pass when stdout contains valid JSON and `nextAction` names the missing service.
- [ ] Lane 7. Run `python tools/chronicle_cli.py --debug dev doctor` with the service available. Save `artifacts/pstack/P00/lane-07.png`. Pass when JSON stays on stdout and request progress stays on stderr.
- [ ] Lane 8. Stop the test command during a run. Save `artifacts/pstack/P00/lane-08.png`. Pass when only the process started by the runner stops.
- [ ] Lane 9. Switch the prototype through its Agent interaction variants. Save `artifacts/pstack/P00/lane-09.png`. Pass when one standing rule can start a proposal without a per-task prompt and human note controls remain available.
- [ ] Lane 10. Open the format-aware prototype and select Markdown, JSON, and a workbook. Save `artifacts/pstack/P00/lane-10.png`. Pass when each format shows its own supported actions and unsupported actions.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Record cold and warm p50 and p95 for note list, note open, search, save acknowledgement, and CLI process startup. Record asset bytes, idle and peak memory, idle CPU, and data growth on both fixture sizes.
- [ ] Probe. Run 30 interleaved measurements against the chosen baseline with one browser build, one API service, and the same fixture.
- [ ] Baseline. Save the raw JSON, fixture generator inputs, machine details, and the code SHA in `artifacts/pstack/P00/perf-baseline.json`.
- [ ] Rule. Fail the baseline run if fewer than 30 valid samples exist or if two reruns of the same baseline differ by more than 10 percent at p95.

**Review gate.** The operator reviews the prototypes and CLI output before the next unit.

- [ ] Post screenshots of the note home, format picker, proactive rule, Agent inbox, and test runner output in chat. Ask the operator to review the human workflow and the later Agent direction.
- [ ] Record a 30 to 60 second video of the selected prototype flow. Save `artifacts/pstack/P00/review.mp4`.

**Merge.**

- [ ] The isolated test runner passes its own isolation checks.
- [ ] The prototype comparison and baseline receipts are attached to the P00 PR.
- [ ] The operator reviews the selected defaults and approves the P00 STACK-READY head.

## Remove the old timeline and graph paths (P01)

**Depends on.** P00. Keep the human Markdown note flow available while removing the old product paths.

**Files.**

- [ ] Remove graph and link routes from `backend/app/api/topics.py` and `backend/app/api/`.
- [ ] Remove `NoteLink`, `relatedNoteIds`, and graph-only columns from `backend/app/models/entities.py`.
- [ ] Remove graph parsers, migration hooks, and graph services from `backend/app/services/timeline.py` and `backend/app/services/legacy_migration.py`.
- [ ] Remove `MindmapEditor.vue`, `CanvasEditor.vue`, `BacklinkPanel.vue`, and graph-specific helpers from `ui/src/`.
- [ ] Remove graph-only packages and stale commands from `package.json`, `backend/`, and `tools/`.

**Build.**

- [ ] Delete graph, free canvas, wikilink, manual-link, and backlink behavior from the active product path.
- [ ] Remove mandatory timeline date, era, event, and sorting assumptions from the note domain. Keep dates as optional metadata only if P00 prototypes show that people need them.
- [ ] Keep note lists, search, tags, properties, collection views, attachments, and ordinary Markdown.
- [ ] Stop application startup from importing or migrating the old database. Use a new empty store for the rebuilt application.
- [ ] Leave `data/timeline.db`, backups, uploads, and old user files untouched. Do not add a compatibility implementation.
- [ ] Make the current CLI Feature Map stop advertising removed operations before any new document API is added.

**You see.**

- [ ] A person opens the rebuilt Web app and sees ordinary notes as the only content type in the core workflow.
- [ ] The old database file remains byte-for-byte unchanged after starting the rebuilt app.
- [ ] `python tools/chronicle_cli.py feature list` no longer exposes graph, canvas, or link operations.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Run `python -m pytest -q` against the disposable database. Confirm tests do not import old graph models.
- [ ] Run `npm run test:ui`, `npm run agent:check`, and `npm run build`.
- [ ] Run `chronicle doctor` and the source grep guard. Confirm no active route, Feature Map entry, or CLI command exposes removed behavior.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.7-xhigh-fast` at the PR head, per the boot recipe.

- [ ] Lane 1. Start with an empty new workspace. Save `artifacts/pstack/P01/lane-01.png`. Pass when the Web app opens without running a legacy migration.
- [ ] Lane 2. Create and reopen a Markdown note. Save `artifacts/pstack/P01/lane-02.png`. Pass when the note survives a refresh.
- [ ] Lane 3. Search for the note. Save `artifacts/pstack/P01/lane-03.png`. Pass when the result opens the same document identity.
- [ ] Lane 4. Add a tag and property. Save `artifacts/pstack/P01/lane-04.png`. Pass when both values survive readback.
- [ ] Lane 5. Move the note into a collection and change the list view. Save `artifacts/pstack/P01/lane-05.png`. Pass when the note remains available.
- [ ] Lane 6. Attach a file and reopen the note. Save `artifacts/pstack/P01/lane-06.png`. Pass when attachment metadata and content references remain intact.
- [ ] Lane 7. Delete and restore the note. Save `artifacts/pstack/P01/lane-07.png`. Pass when restore returns the same document ID.
- [ ] Lane 8. Request an old graph route. Save `artifacts/pstack/P01/lane-08.png`. Pass when the route is absent and the API returns a stable unsupported or not-found error.
- [ ] Lane 9. Run `python tools/chronicle_cli.py api list`. Save `artifacts/pstack/P01/lane-09.png`. Pass when no removed graph or timeline-only operation is listed.
- [ ] Lane 10. Compare the old database hash before and after the app run. Save `artifacts/pstack/P01/lane-10.png`. Pass when the hashes match.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Measure the surviving note list, open, search, and save flows on the P00 fixture.
- [ ] Probe. Interleave 30 trunk and 30 head samples using the same app build, data, and browser.
- [ ] Baseline. Read the original values from `artifacts/pstack/P00/perf-baseline.json`.
- [ ] Rule. Fail if any surviving core note p95 regresses by more than 10 percent or any old database write occurs.

**Review gate.** The operator reviews the simplified note workflow before merge.

- [ ] Post screenshots for note list, editor, search, and restored note in chat for the operator.
- [ ] Record a 30 to 60 second video of create, edit, and reopen for the operator. Save `artifacts/pstack/P01/review.mp4`.

**Merge.**

- [ ] The new app starts without touching the old database.
- [ ] Removed graph and timeline operations have no remaining active callers.
- [ ] The operator approves the P01 STACK-READY head.

## Define the document model and one API contract (P02)

**Depends on.** P01. Resolve the hosting and storage gates in Appendix C before implementation.

**Files.**

- [ ] Define the canonical document model in `backend/app/models/` and `backend/app/schemas/`.
- [ ] Define document operations in `backend/app/api/` and `backend/app/services/`.
- [ ] Generate the Web client types from the FastAPI OpenAPI schema under `ui/src/types/`.
- [ ] Define a format adapter boundary under `backend/app/content_formats/`.
- [ ] Update `backend/app/main.py` to use the new storage configuration without automatic legacy imports.

**Build.**

- [ ] Give each document a stable ID, workspace scope, content format, format version, metadata, revision, and deletion state.
- [ ] Store format-specific content without a second Markdown-to-JSON body or dual-write path.
- [ ] Define create, list, read, update, search, attachment, version, and restore operations with typed request and response schemas.
- [ ] Use a revision or ETag precondition for writes and an idempotency key for retries.
- [ ] Return stable error codes, field details, request IDs, and executable `nextAction` values.
- [ ] Generate CLI and Web request and response types from the same API schema. Keep Feature Map metadata focused on user capabilities and operation IDs.
- [ ] Keep one canonical storage implementation for the selected deployment. Do not preserve SQLite and a new database as parallel application stores.

**You see.**

- [ ] The Web client and CLI create, read, update, search, and restore the same document through the same HTTP API.
- [ ] A stale write fails with the current revision and does not overwrite newer content.
- [ ] A repeated idempotent request returns the original result rather than creating another document.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Run `python -m pytest -q tests/test_document_api.py tests/test_document_storage.py`.
- [ ] Run `python tools/generate_api_types.py --check` and the API schema drift check.
- [ ] Run `npm run test:ui` against the generated API client.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.7-xhigh-fast` at the PR head, per the boot recipe.

- [ ] Lane 1. Create a document with the Markdown format. Save `artifacts/pstack/P02/lane-01.png`. Pass when the API returns a stable ID and revision.
- [ ] Lane 2. Read the document from the Web. Save `artifacts/pstack/P02/lane-02.png`. Pass when the content and revision match the API response.
- [ ] Lane 3. Read the same document with CLI. Save `artifacts/pstack/P02/lane-03.png`. Pass when CLI returns the same ID, format, and revision.
- [ ] Lane 4. Update with the current revision. Save `artifacts/pstack/P02/lane-04.png`. Pass when readback shows exactly one new revision.
- [ ] Lane 5. Update with a stale revision. Save `artifacts/pstack/P02/lane-05.png`. Pass when the API rejects it without changing content.
- [ ] Lane 6. Replay the same idempotency key. Save `artifacts/pstack/P02/lane-06.png`. Pass when the original result is returned.
- [ ] Lane 7. Send an unknown content format. Save `artifacts/pstack/P02/lane-07.png`. Pass when the API returns a typed unsupported-format error and no document.
- [ ] Lane 8. Request a document from another workspace. Save `artifacts/pstack/P02/lane-08.png`. Pass when the API denies access without revealing content.
- [ ] Lane 9. Send an invalid field through Web and CLI. Save `artifacts/pstack/P02/lane-09.png`. Pass when both report the same schema path and error code.
- [ ] Lane 10. Stop the client after submitting an update and replay by idempotency key. Save `artifacts/pstack/P02/lane-10.png`. Pass when readback resolves the unknown result without a duplicate write.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Measure document list, open, search, update, and readback p50 and p95 on the 1,000 and 10,000 document fixtures.
- [ ] Probe. Interleave 30 trunk and 30 head requests with the same fixture, storage engine, and service resources.
- [ ] Baseline. Use the P00 measurements and add the selected database's version, indexes, and query plan to the receipt.
- [ ] Rule. Fail on a surviving-flow p95 regression above 10 percent. Set a new-format absolute budget in P05 before implementing that format.

**Review gate.** The operator reviews the document contract before merge.

- [ ] Post screenshots, the OpenAPI diff, generated type diff, and two Web-to-CLI readback receipts in chat for the operator.
- [ ] Record a 30 to 60 second video of creating and revising one Markdown document for the operator. Save `artifacts/pstack/P02/review.mp4`.

**Merge.**

- [ ] One API schema produces both client contracts.
- [ ] The old database remains untouched and the new store starts empty.
- [ ] The operator approves the P02 STACK-READY head.

## Deliver the complete human Markdown workflow (P03)

**Depends on.** P02. Keep human note actions complete even when no Agent is connected.

**Files.**

- [ ] Replace the timeline-centered page in `ui/src/pages/NotesPage.vue` with the approved note workspace.
- [ ] Organize note view, editor, search, collection, and attachment code under `ui/src/features/notes/`.
- [ ] Update the shared client in `ui/src/composables/useApi.js` and the note store in `ui/src/composables/`.
- [ ] Add browser behavior cases under `ui/tests/`.
- [ ] Add matching registered operations and scenarios under `backend/app/features.py`.

**Build.**

- [ ] Make Markdown the default create and edit format. Keep content portable as Markdown and keep metadata separate.
- [ ] Support create, read, edit, save status, search, sort, tags, properties, collections, attachments, export, version history, trash, and restore.
- [ ] Show workspace storage use for note content, attachments, revisions, and rebuildable indexes. Provide export and backup paths without silently deleting user data.
- [ ] Keep date and timeline views optional. Do not make a note's existence depend on a date, era, or notebook type.
- [ ] Show drafts and revision conflicts without losing local text. Offer a clear reread and compare path.
- [ ] Make the common create, open, edit, and search tasks work by keyboard and on narrow screens.
- [ ] Use one Web API client and one CLI operation definition for each user action.

**You see.**

- [ ] A person can manage ordinary notes from a clean workspace without seeing Agent setup or legacy graph controls.
- [ ] Save, error, conflict, and recovery states remain visible until the API confirms the result.
- [ ] The workspace reports storage use by category and lets the user find large attachments.
- [ ] A note still opens and edits as Markdown when an Agent provider is unavailable.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Run `npm run test:ui -- --project=notes` for the Markdown note flows.
- [ ] Run `python -m pytest -q tests/test_document_api.py` for the matching HTTP operations.
- [ ] Run `python tools/chronicle_cli.py scenario list` and confirm that it names the registered note scenarios.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.7-xhigh-fast` at the PR head, per the boot recipe.

- [ ] Lane 1. Create a Markdown note from an empty workspace. Save `artifacts/pstack/P03/lane-01.png`. Pass when the new note opens in the editor.
- [ ] Lane 2. Type and save a Markdown heading and list. Save `artifacts/pstack/P03/lane-02.png`. Pass when rendered text and stored Markdown agree after refresh.
- [ ] Lane 3. Edit an existing note and navigate away. Save `artifacts/pstack/P03/lane-03.png`. Pass when the confirmed content is present on reopen.
- [ ] Lane 4. Search for a phrase in note content. Save `artifacts/pstack/P03/lane-04.png`. Pass when the result opens the correct document.
- [ ] Lane 5. Filter by a tag and property. Save `artifacts/pstack/P03/lane-05.png`. Pass when the collection contains only matching notes.
- [ ] Lane 6. Attach and reopen a file. Save `artifacts/pstack/P03/lane-06.png`. Pass when the attachment opens and its metadata is unchanged.
- [ ] Lane 7. Delete and restore a note. Save `artifacts/pstack/P03/lane-07.png`. Pass when content and identity match the pre-delete revision.
- [ ] Lane 8. Edit the same document from two browser sessions. Save `artifacts/pstack/P03/lane-08.png`. Pass when the second save shows a conflict and preserves both drafts.
- [ ] Lane 9. Complete create, edit, and search on a narrow viewport with keyboard only. Save `artifacts/pstack/P03/lane-09.png`. Pass when all controls expose names and focus remains visible.
- [ ] Lane 10. Run the matching CLI create, read, edit, and search scenario. Save `artifacts/pstack/P03/lane-10.png`. Pass when CLI readback matches the Web document ID and revision.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Measure first note-list interactive state, editor input delay, save acknowledgement, search p95, and storage growth with 10,000 documents.
- [ ] Probe. Interleave 30 browser runs on trunk and head with the same browser version, machine, viewport, fixture, and warm-cache policy.
- [ ] Baseline. Read the P00 receipts and record cold and warm values separately.
- [ ] Rule. Fail if p95 regresses over 10 percent or if first interactive state exceeds 2 seconds, input delay exceeds 100 milliseconds, or save acknowledgement exceeds 800 milliseconds.

**Review gate.** The operator reviews the human note workflow before merge.

- [ ] Post the empty workspace, editor, search, conflict, and mobile screenshots in chat for the operator.
- [ ] Record a 30 to 60 second video of create, edit, search, and restore for the operator. Save `artifacts/pstack/P03/review.mp4`.

**Merge.**

- [ ] All human note flows pass without an Agent provider.
- [ ] The CLI readback matches the Web API state.
- [ ] The operator approves the P03 STACK-READY head.

## Complete the product and developer CLI (P04)

**Depends on.** P02 and P03. Complete the named CLI path for every human note operation before adding Agent runtime commands.

**Files.**

- [ ] Replace the monolithic entry point in `tools/chronicle_cli.py` with modules under `tools/chronicle/`.
- [ ] Generate CLI argument and response validators from the OpenAPI schema under `tools/chronicle/generated/`.
- [ ] Define capability and scenario metadata under `backend/app/features.py`.
- [ ] Add CLI behavioral cases under `tools/chronicle/tests/`.
- [ ] Register the browser validation command in `package.json` and keep the Python suites under `tools/chronicle/tests/`.

**Build.**

- [ ] Add product command groups for feature discovery, workspaces, documents, collections, attachments, export, versions, trash, and restore.
- [ ] Add developer command groups for `doctor`, `test`, `scenario`, `debug`, and `perf`.
- [ ] Keep Agent task, rule, and proposal commands out of this phase. Add them only after the human note CLI contract is complete.
- [ ] Derive command arguments and validation from the same schema used by FastAPI. Remove the manual request and response model maps.
- [ ] Use registered operation IDs and domain commands. Do not expose arbitrary URL, SQL, shell, or page-script arguments.
- [ ] Return stable JSON with status, operation, resource ID, revision, failure code, `nextAction`, and optional receipt paths.
- [ ] Write long progress to stderr. Redact credentials and note content from default diagnostics.
- [ ] Let the dev runner start and stop only its owned isolated services. Do not let product commands start the legacy app against user data.
- [ ] Keep feature addition mechanical. A new capability must register its schema, command, scenario, error mapping, and live receipt in one reviewable unit.

**You see.**

- [ ] Every active human note capability has a named CLI command with schema validation and readback.
- [ ] CLI errors return a stable code and executable `nextAction` without asking a caller to infer success from prose.
- [ ] CI reports complete coverage only when every configured backend, browser, CLI, and format suite ran and passed.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Run `python -m pytest -q tools/chronicle/tests tests`.
- [ ] Run the configured suites through their repository test runners and inspect their machine-readable result.
- [ ] Run the generated contract drift check and prove that a new OpenAPI operation fails the check until its Feature Map and CLI command are registered.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.7-xhigh-fast` at the PR head, per the boot recipe.

- [ ] Lane 1. Run `python tools/chronicle_cli.py feature list`. Save `artifacts/pstack/P04/lane-01.png`. Pass when every active capability is returned with no manual JSON parsing.
- [ ] Lane 2. Run `python tools/chronicle_cli.py feature describe notes`. Save `artifacts/pstack/P04/lane-02.png`. Pass when UI route, operation IDs, schemas, permissions, and scenarios appear.
- [ ] Lane 3. Create a note with CLI. Save `artifacts/pstack/P04/lane-03.png`. Pass when the CLI reads back the same document ID and revision.
- [ ] Lane 4. Run a stale document update. Save `artifacts/pstack/P04/lane-04.png`. Pass when JSON returns `version_conflict` and a reread action.
- [ ] Lane 5. Update a note property through CLI. Save `artifacts/pstack/P04/lane-05.png`. Pass when Web readback shows the same property and revision.
- [ ] Lane 6. Delete and restore a note through CLI. Save `artifacts/pstack/P04/lane-06.png`. Pass when restore returns the same document ID and content.
- [ ] Lane 7. Run a malformed command. Save `artifacts/pstack/P04/lane-07.png`. Pass when stdout remains one JSON error and the exit code is nonzero.
- [ ] Lane 8. Run a missing-service diagnostic. Save `artifacts/pstack/P04/lane-08.png`. Pass when the CLI returns `service_unavailable` with an executable next action.
- [ ] Lane 9. Run the CLI under `--debug`. Save `artifacts/pstack/P04/lane-09.png`. Pass when progress appears on stderr and secrets and note bodies do not.
- [ ] Lane 10. Add a fixture capability without adding a CLI command. Save `artifacts/pstack/P04/lane-10.png`. Pass when `doctor` reports the gap and exits nonzero.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Measure CLI startup, feature list, document read, document write and readback, and scenario run duration.
- [ ] Probe. Interleave 30 runs on trunk and head with the same Python, service, workspace, and fixture.
- [ ] Baseline. Compare product command latency with direct HTTP latency and store both values.
- [ ] Rule. Fail if CLI overhead exceeds 250 milliseconds for local read commands, any result differs from direct API readback, or p95 regresses over 10 percent.

**Review gate.** The operator reviews the CLI command and JSON result surfaces before merge.

- [ ] Post screenshots of terminal help, success, validation failure, conflict, and debug redaction for the operator.
- [ ] Record a 30 to 60 second video of note create, edit, search, and restore through the CLI. Save `artifacts/pstack/P04/review.mp4`.

**Merge.**

- [ ] Every active Feature Map operation has a schema-validated named CLI path or an explicit unsupported status with a reason.
- [ ] All write paths keep user confirmation and version checks.
- [ ] The operator approves the P04 STACK-READY head.

## Add JSON and spreadsheet format adapters (P05)

**Depends on.** P02 through P04. Start after the Markdown workflow, API schemas, and human note CLI contracts are stable.

**Files.**

- [ ] Add the format contract under `backend/app/content_formats/`.
- [ ] Add JSON and workbook adapters under `backend/app/content_formats/json_document.py` and `backend/app/content_formats/xlsx_document.py`.
- [ ] Add format-aware UI components under `ui/src/features/content-formats/`.
- [ ] Add format-aware CLI operations under `tools/chronicle/formats/`.
- [ ] Add JSON and workbook fixtures under `tests/fixtures/formats/` and `ui/tests/fixtures/formats/`.

**Build.**

- [ ] Keep one document identity, permission model, revision model, and API. Select behavior through the registered format adapter.
- [ ] Support JSON validation, structured read and edit, and lossless export.
- [ ] Support the P00-approved Excel scope for `.xlsx` workbooks. Preserve workbook sheets, formulas, styles, and unsupported features when the first release only previews them.
- [ ] Keep format-specific UI simple. Do not force JSON or spreadsheet content into the Markdown editor.
- [ ] Give each format explicit read, edit, validate, preview, import, and export capabilities.
- [ ] Return a typed unsupported-operation error when a format does not support an action.
- [ ] Add the same registered operations to Web and CLI without format-specific storage or API duplication.

**You see.**

- [ ] A person can create and open Markdown, JSON, and the approved workbook format in the same document list.
- [ ] The correct editor opens for each format. Unsupported actions remain visible with a clear reason.
- [ ] Each format declares its supported actions so the later Agent phase can use the same capability contract.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Run `python -m pytest -q tests/test_format_json.py tests/test_format_xlsx.py`.
- [ ] Run `npm run test:ui -- --project=formats` and `python tools/chronicle_cli.py dev scenario run formats`.
- [ ] Compare imported and exported JSON and workbook fixtures by parsed structure and binary preservation rules.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.7-xhigh-fast` at the PR head, per the boot recipe.

- [ ] Lane 1. Create a JSON document with a valid schema. Save `artifacts/pstack/P05/lane-01.png`. Pass when the editor and CLI return the same parsed value.
- [ ] Lane 2. Open invalid JSON. Save `artifacts/pstack/P05/lane-02.png`. Pass when the user sees the parse location and no partial write occurs.
- [ ] Lane 3. Edit one JSON field. Save `artifacts/pstack/P05/lane-03.png`. Pass when schema validation and revision readback pass.
- [ ] Lane 4. Export the JSON document. Save `artifacts/pstack/P05/lane-04.png`. Pass when parsed export equals the stored content.
- [ ] Lane 5. Import a valid `.xlsx` fixture. Save `artifacts/pstack/P05/lane-05.png`. Pass when sheets and values match the source workbook.
- [ ] Lane 6. Preview a workbook with formulas and styles. Save `artifacts/pstack/P05/lane-06.png`. Pass when the preview preserves supported workbook data and declares unsupported features.
- [ ] Lane 7. Edit one supported cell. Save `artifacts/pstack/P05/lane-07.png`. Pass when readback changes only that cell and returns one new revision for the same document ID.
- [ ] Lane 8. Ask the CLI for an unsupported workbook action. Save `artifacts/pstack/P05/lane-08.png`. Pass when it returns `unsupported_operation` and a next action.
- [ ] Lane 9. Submit a corrupted workbook. Save `artifacts/pstack/P05/lane-09.png`. Pass when the file is rejected without replacing the original.
- [ ] Lane 10. Run the same JSON and workbook read scenarios through Web and CLI. Save `artifacts/pstack/P05/lane-10.png`. Pass when document IDs and revisions match.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Measure JSON validation and export for a 1 MB document and workbook preview for a 50,000-cell fixture.
- [ ] Probe. Run 30 interleaved Web and CLI operations with the same fixtures and storage engine.
- [ ] Baseline. Record file size, cell count, runtime, memory peak, and the adapter version with each result.
- [ ] Rule. Fail if JSON validation p95 exceeds 500 milliseconds, workbook preview p95 exceeds 2 seconds, memory exceeds 256 MB, or the operation regresses over 10 percent.

**Review gate.** The operator reviews each editor and file-preservation behavior before merge.

- [ ] Post screenshots for JSON validation, workbook preview, cell edit, and unsupported operations for the operator.
- [ ] Record a 30 to 60 second video of opening and editing one JSON document and one workbook for the operator. Save `artifacts/pstack/P05/review.mp4`.

**Merge.**

- [ ] Markdown behavior is unchanged.
- [ ] JSON and workbook content round-trip under their declared format contracts.
- [ ] The operator approves the P05 STACK-READY head.

## Add proactive Agent collaboration (P06)

**Depends on.** P02 through P05. Start only after the human note workflow, API contract, CLI, and approved format adapters are stable.

**Files.**

- [ ] Add delegation policy, trigger event, task run, session, proposal, progress event, and operation receipt models under `backend/app/models/` and `backend/app/schemas/`.
- [ ] Add the durable event handoff, task queue, lease handling, and Agent connector under `backend/app/agent_runtime/`.
- [ ] Add policy, task, session, and proposal operations under `backend/app/api/`.
- [ ] Add the Agent activity inbox, policy controls, and proposal review under `ui/src/features/agent/`.
- [ ] Add Agent operations and scenarios to `backend/app/features.py` and `tools/chronicle/`.

**Build.**

- [ ] Keep long-lived delegation policies, trigger events, task runs, conversations, proposals, and write receipts as separate records with explicit lifecycles.
- [ ] Let a person create a standing delegation with a goal, document scope, trigger rules, allowed operations, run limits, notification settings, provider, and enabled state.
- [ ] Start runs from committed note events or scheduled checks. Do not trigger model work on every keystroke.
- [ ] Debounce and coalesce matching events. Record actor, cause, and idempotency identity so retries do not duplicate runs and an accepted proposal does not loop back into the same rule by default.
- [ ] Persist the event outbox and task queue in the selected canonical database before dispatch. Do not add a separate broker by default; add one only after P00 load measurements show a need.
- [ ] Let an authenticated external Agent connector claim each run with a lease, report progress, ask questions, and submit proposals. Recover expired leases and resume or report failure after a restart.
- [ ] Keep task execution independent of an open browser. If the selected local service is stopped, retain queued work and resume it when the service returns.
- [ ] Give each run a server-issued grant with a frozen workspace, document scope, allowed operations, and base revisions. Enforce the grant in the API and document service.
- [ ] Enforce the grant at every operation boundary. Treat Feature Map permissions as discovery metadata, not as the security check.
- [ ] Let an Agent use registered schemas and named operations. Do not give it database access, arbitrary HTTP forwarding, shell access, or page scripts.
- [ ] Store ordered progress events with replay cursors. Let an Agent ask a question, wait for a reply, and continue the same task without a new task prompt.
- [ ] Show queued, running, waiting for the user, completed, failed, cancelled, and stale states in an Agent inbox. Let the user pause or revoke a standing delegation.
- [ ] Deliver notifications only under the standing rule's user-selected notification settings. Preserve pending proposals and their source revisions until the user resolves them.
- [ ] Store each proposal separately with its target document, base revision, bounded change, explanation, and human decision.
- [ ] Require a human to accept or reject every proposed note mutation. Only the human acceptance operation can call the conditional write API; the Agent cannot accept its own proposal.
- [ ] Apply accepted changes only when the base revision still matches. Use an idempotency key and readback to resolve an unknown result.
- [ ] Record per-run usage and workspace storage. Bound active runs, context size, event retention, and provider spend using the P00-approved budgets.
- [ ] Keep model execution outside the core notebook process. Use the existing scoped search and read operations for task context. Do not add a vector database or copy the whole workspace into a prompt by default.
- [ ] Use a fake connector in default tests and require separate authorization for credentials or real provider costs.

**You see.**

- [ ] A person can authorize a standing rule once and receive an Agent proposal after a matching event without starting each task manually.
- [ ] The user can inspect why a run started, which notes it read, what it proposed, and which note revision the proposal uses.
- [ ] The user can pause a rule, reply to an Agent question, and review pending proposals from the inbox.
- [ ] Closing the browser does not lose queued work or progress while the selected Chronicle service remains available.
- [ ] The notebook remains usable when no Agent connector or provider is available.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Run `python -m pytest -q tests/test_agent_policies.py tests/test_agent_runs.py tests/test_agent_sessions.py tests/test_proposals.py` with the fake connector.
- [ ] Run `npm run test:ui -- --project=agent` against the local fake connector.
- [ ] Verify that the fake-connector test path never reads real credentials.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.7-xhigh-fast` at the PR head, per the boot recipe.

- [ ] Lane 1. Create a standing rule for one authorized note. Save `artifacts/pstack/P06/lane-01.png`. Pass when the rule stores its goal, scope, trigger, and allowed operations.
- [ ] Lane 2. Save the note after enabling the rule. Save `artifacts/pstack/P06/lane-02.png`. Pass when one run starts without a per-task Agent prompt.
- [ ] Lane 3. Replay the same note event and restart the dispatcher. Save `artifacts/pstack/P06/lane-03.png`. Pass when the event produces one run and no trigger loop.
- [ ] Lane 4. Close the browser while the Chronicle service stays available. Save `artifacts/pstack/P06/lane-04.png`. Pass when the run completes and its progress appears after reconnect.
- [ ] Lane 5. Ask the Agent to read a document outside its grant. Save `artifacts/pstack/P06/lane-05.png`. Pass when the API denies access without revealing content.
- [ ] Lane 6. Submit a bounded proposal. Save `artifacts/pstack/P06/lane-06.png`. Pass when the proposal names the exact document and base revision.
- [ ] Lane 7. Reject the proposal. Save `artifacts/pstack/P06/lane-07.png`. Pass when note content and revision remain unchanged.
- [ ] Lane 8. Accept the proposal as the human user. Save `artifacts/pstack/P06/lane-08.png`. Pass when one new revision is written and readback matches.
- [ ] Lane 9. Edit the note before accepting an old proposal. Save `artifacts/pstack/P06/lane-09.png`. Pass when the proposal becomes stale and preserves the newer text.
- [ ] Lane 10. Interrupt a claimed run and replay its event. Save `artifacts/pstack/P06/lane-10.png`. Pass when lease recovery produces one final result and no duplicate write.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Measure event-to-queue time, queue wait, first status, event replay, proposal review, idle Worker CPU and memory, peak run memory, and stored bytes per run.
- [ ] Probe. Interleave 30 fake-connector runs on trunk and head. Exclude external provider wait time from application latency.
- [ ] Baseline. Use the P00 resource and API receipts. Record the fake connector version, fixture, service mode, and provider cost as zero.
- [ ] Rule. Fail if application first-status p95 exceeds 500 milliseconds, replay p95 exceeds 500 milliseconds, or the Worker exceeds a memory, CPU, storage, or run budget approved from P00 measurements.

**Review gate.** The operator reviews the proactive rule, Agent inbox, progress, and proposal flow before merge.

- [ ] Post screenshots for rule setup, automatic run, inbox, proposal diff, stale conflict, accept, and reject for the operator.
- [ ] Record a 30 to 60 second video showing an event-triggered proposal and its human review. Save `artifacts/pstack/P06/review.mp4`.

**Merge.**

- [ ] Fake-connector scenarios pass with no credentials or external charges.
- [ ] The Agent cannot write note content or accept its own proposal.
- [ ] The operator approves the P06 STACK-READY head and the provider authorization gate remains closed.

## Harden Web delivery and pass the release gate (P07)

**Depends on.** P01 through P06. Do not start the desktop shell before this gate passes.

**Files.**

- [ ] Add security and load cases under `tests/security/`, `tests/load/`, and `ui/tests/`.
- [ ] Add redacted diagnostics and operational health to `backend/app/core/` and `tools/chronicle/`.
- [ ] Add release and performance checks under `tools/bench/` and the CI configuration.
- [ ] Update `README.md` and `docs/plan/` with the verified Web commands and measured budgets.

**Build.**

- [ ] Verify workspace isolation, Agent scopes, provider secret redaction, request limits, attachment limits, and session cancellation.
- [ ] Verify service restart recovery, duplicate event handling, task budgets, Agent self-trigger prevention, and the selected service mode's behavior after the browser closes.
- [ ] Verify restore and export paths for user-created Web data. The release does not import or delete the old database.
- [ ] Run the full browser, API, CLI, and format suites against the same release candidate.
- [ ] Measure all P00 resource and performance cases on the release candidate and compare them to the recorded budgets.
- [ ] Keep real LLM usage disabled in CI. Require explicit provider, credential, and spend approval for live provider tests.
- [ ] Pass the Web exit gate before planning implementation work for desktop.

**You see.**

- [ ] A person can complete all core note workflows without an Agent connection.
- [ ] An enabled standing rule can start a scoped Agent task without a per-task prompt and present a proposal for human review.
- [ ] The application reports storage use and Agent run state without requiring a separate monitoring service.
- [ ] CI reports exactly which product, browser, API, CLI, format, and performance checks passed.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Run the configured suites against a fresh isolated workspace through their repository test runners.
- [ ] Run `python tools/chronicle_cli.py dev doctor` and require zero schema or capability drift.
- [ ] Run the security, browser, format, and provider-failure suites with no production credentials.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.7-xhigh-fast` at the PR head, per the boot recipe.

- [ ] Lane 1. Sign in to a test workspace and create a Markdown note. Save `artifacts/pstack/P07/lane-01.png`. Pass when the workspace contains only its own data.
- [ ] Lane 2. Search and open a note in a 10,000-document workspace. Save `artifacts/pstack/P07/lane-02.png`. Pass when identity and revision match readback.
- [ ] Lane 3. Run a complete Agent proposal lifecycle. Save `artifacts/pstack/P07/lane-03.png`. Pass when every event and revision is auditable.
- [ ] Lane 4. Deny an Agent scope violation. Save `artifacts/pstack/P07/lane-04.png`. Pass when no content or metadata leaks.
- [ ] Lane 5. Retry an unknown-result update. Save `artifacts/pstack/P07/lane-05.png`. Pass when idempotency prevents a duplicate write.
- [ ] Lane 6. Disconnect the browser during a running session. Save `artifacts/pstack/P07/lane-06.png`. Pass when reconnect restores state from its cursor.
- [ ] Lane 7. Export a workspace and verify the output. Save `artifacts/pstack/P07/lane-07.png`. Pass when notes and file references match the export receipt.
- [ ] Lane 8. Restart the Web app with the new store. Save `artifacts/pstack/P07/lane-08.png`. Pass when user data remains readable and no legacy migration runs.
- [ ] Lane 9. Run all active CLI scenarios against the release candidate. Save `artifacts/pstack/P07/lane-09.png`. Pass when coverage is complete and every receipt links to a real API readback.
- [ ] Lane 10. Run keyboard and narrow viewport checks for note and Agent review flows. Save `artifacts/pstack/P07/lane-10.png`. Pass when no workflow loses content or hides its recovery action.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Re-measure Web first interactive state, note list, open, search, save, Agent first status, CLI operations, JSON, workbook preview, idle CPU and memory, and storage growth p50 and p95 where applicable.
- [ ] Probe. Run 30 interleaved trunk and release candidate samples per metric with the same fixture and environment.
- [ ] Baseline. Use the P00 baseline and record the code SHA, fixture SHA, environment, and each raw result.
- [ ] Rule. Fail if a core p95 regresses over 10 percent, first interactive state exceeds 2 seconds, search exceeds 500 milliseconds, save exceeds 800 milliseconds, or Agent first status exceeds 500 milliseconds excluding provider time.

**Review gate.** The operator reviews the Web release candidate before merge.

- [ ] Post the full core workflow screenshots and the final Feature Map and CLI coverage receipt in chat for the operator.
- [ ] Record a 30 to 60 second video of human note use, Agent review, and one format-specific flow for the operator. Save `artifacts/pstack/P07/review.mp4`.

**Merge.**

- [ ] All core human, Agent, and CLI scenarios pass against the release candidate.
- [ ] The old data store remains untouched and the new store has a tested backup and export path.
- [ ] The operator approves the P07 Web exit gate. Keep P08 parked until this approval.

## Close the program

- [ ] Confirm P00 through P07 are verified against their current PR head SHAs.
- [ ] Confirm every active Feature Map capability has matching UI or CLI access, typed API schemas, a live scenario, a failure path, and a readback assertion.
- [ ] Confirm the old database was neither migrated, overwritten, nor deleted.
- [ ] Confirm the Web exit gate passes before opening the desktop follow-up.
- [ ] Send the operator the stack links, verification ledger, measured budgets, open decisions, and the P08 desktop trigger.

## Appendix A. Prototype evidence

The prior co-writing prototype compared selection editing, an Agent side panel, and a hybrid layout at 1920 by 1080. Its README reports Playwright screenshots and no console errors. The recommendation is the hybrid layout. Selection editing supports short changes. The side panel supports longer tasks and multiple turns.

The prototype is an external artifact, not a tracked product branch. This plan was checked against source snapshot `main@400cfdd`. The artifact hashes below identify the exact files. They do not prove that the UI was integrated with real APIs or that saves persisted.

- [Prototype README](C:/Users/clown/.codex/visualizations/2026/10/26/01a175d2-a0e7-7d51-a370-6356181c0fee/README.md). SHA-256 `c058d984e7fe148167410cdff8c1154a46a02961441c181ee963e7ae5e5bcbdb`.
- [Selection editing screenshot](C:/Users/clown/.codex/visualizations/2026/10/26/01a175d2-a0e7-7d51-a370-6356181c0fee/coauthor-inline.png). SHA-256 `071377caacd89fad1bd0b3cee4239f66b5ad7def8637d3879ac9987bda00fd1f`.
- [Agent side panel screenshot](C:/Users/clown/.codex/visualizations/2026/10/26/01a175d2-a0e7-7d51-a370-6356181c0fee/coauthor-panel.png). SHA-256 `78e1c8cfabaa4cf81774d64cd96492e5ac52152325f440b85bad1da2d82034a3`.
- [Hybrid layout screenshot](C:/Users/clown/.codex/visualizations/2026/10/26/01a175d2-a0e7-7d51-a370-6356181c0fee/coauthor-hybrid.png). SHA-256 `d1edc2521d59374b1163440b6ba60b7296e83a40eb04f594e0b095b64421ade0`.
- [Prototype HTML](C:/Users/clown/.codex/visualizations/2026/10/26/01a175d2-a0e7-7d51-a370-6356181c0fee/coauthor-options.html). SHA-256 `8388a2ed394b8e9b1bde8fa526ff2ac0509228a75bdd8aba4ed113cf73d6f06e`.

The current prototype proves only that the hybrid interaction fits the note editor. It does not prove real Agent streaming, proactive triggers, authorization, save review, stale proposal rejection, responsive behavior, or persistence. P00 must prototype the human note home and format picker. It must also prototype the later standing-rule and inbox flow without implementing Agent runtime. P06 starts only after the notebook, API, CLI, and format contracts pass.

## Appendix B. Product defaults and alternatives

| Decision | Current direction | Alternative to keep open |
| --- | --- | --- |
| Delivery order | Complete Markdown notes, typed API, named CLI, JSON, and `.xlsx` before adding Agent runtime in P06. | Defer JSON and `.xlsx` until after P07 if their measured cost blocks the notebook release. |
| App hosting | Resolve local-first versus hosted deployment in P00 before P02. A local service runs rules while the service is available. | Hosted Chronicle keeps rules active after the browser closes. |
| Agent execution | Chronicle owns rules, permissions, runs, proposals, and receipts. An external Agent runtime claims scoped tasks. | Add a Chronicle-managed provider adapter only after the credential and spend policy is approved. |
| Agent authority | A standing rule can start work, read its scope, ask questions, and submit proposals. A human confirms every note write. | Allow automatic writes only for named operations after an explicit change to the product boundary. |
| Canonical storage | Choose one database and one attachment store after the P00 footprint and load baseline. Do not keep SQLite and a server database as parallel product stores. | Select the other supported deployment profile before P02. |
| Agent resource use | Wake execution for eligible work. Bound context, active runs, stored events, and provider spend with P00-approved budgets. | Add more frequent checks only when a measured user task needs them. |
| First workbook format | Add `.xlsx` preview and selected edits in P05, before Agent runtime. | Add legacy `.xls` import if real user files require it. |
| Desktop behavior | Start as an online client of the stable Web API after P07. | Add offline edits and sync in a separate program after conflict tests. |
| Note collections | Keep tags, properties, folders, and collection views. Keep dates optional. | Add more collection types only when a real note task needs them. |

The plan does not select a cloud vendor, canonical database, Agent connector, or billing policy. P00 records the hardware and workload profile, then the operator selects a deployment and storage mode before P02. P06 uses a deterministic connector by default. Real model calls, credentials, and provider costs require separate authorization.

## Appendix C. Baseline risks and gates

- The current branch is `main` at `400cfdd`. The local `origin/main` ref is `6c1bcf449cf4356ae622604dcd9948a695db6d00`, and the local branch has 13 commits not in that ref. The working tree also has many modifications, deletions, and untracked files. P00 must inspect each existing change and select a base before creating a worktree. Do not reset this tree.
- The user has said that old data can be ignored. The new application will use an empty store and will not import the old `data/timeline.db`. The old database, attachments, and backups remain untouched unless the user later requests deletion.
- `backend/app/main.py` currently runs legacy migrations during startup. P01 must remove that startup path before any test or dev command can target user data.
- Current models and UI still include `bodyMarkdown`, `bodyJson`, `mindmap`, `canvas`, `NoteLink`, `relatedNoteIds`, timeline dates, and the old editor. P01 removes the old concepts before P02 builds the new document model.
- `tools/chronicle_cli.py` currently contains a manual schema map, a read-only operation path, and scenario-specific branches. The current Feature Map has 33 API operations but only a small set of read scenarios. P04 must replace the manual growth pattern before P06 adds Agent task commands.
- The existing README describes a local-first app with an external Agent, while an earlier draft of this program selected hosted workspaces. P00 must resolve the deployment mode before P02 because it controls storage, service availability, and whether rules can run after a browser or local service stops.
- The current plan has no idle memory, idle CPU, asset-size, storage-growth, or Agent run-cost budgets. P00 must record these budgets before P06 adds background work.
- The current API and Feature Map have no Agent policies, durable triggers, task queue, session, or proposal API. P06 must add server-enforced grants, retry and deduplication, and an Agent inbox after the notebook API and CLI are complete.
- A saved proposal can generate another note event when a human accepts it. P06 must record causal identity and prevent the same rule from starting an unbounded run loop.
- `package.json` has no `test:ui` script, and the current worktree marks prior `ui/tests/` files as deleted. P00 must define a fresh browser test suite rather than restoring the removed tests without review.
- Pstack references `control-ui` and `control-cli` from `cursor-team-kit`, but those control skills are not present under `vendor/pstack`. P00 must verify the installed control tools. If they are unavailable, use the owned Playwright browser runner and CLI subprocess runner and record the fallback.
- The prior prototype only covers co-writing layout. The new note home, format picker, proactive rule setup, inbox, workspace boundaries, and service mode remain unproven.
- Initial performance thresholds are project targets, not measurements. P00 records asset bytes, memory, CPU, storage growth, and API latency before any change. P03 through P07 compare the same fixture and environment. Do not report a speedup without the raw runs and limiter.
- Real model calls, credentials, user data, provider costs, and external storage writes require separate authorization. Test lanes use a deterministic local provider.
- The desktop client is outside P00 through P07. Start P08 only after P07 passes and the operator chooses online-only or offline behavior.

## Appendix D. Source and playbook references

- Product and repository rules live in `AGENTS.md`.
- The current product direction lives in `docs/plan/agent-friendly-notes-direction.md`.
- Current routes live in `backend/app/api/` and are registered in `backend/app/main.py`.
- Current document shapes live in `backend/app/models/entities.py` and `backend/app/schemas/common.py`.
- Current note logic lives in `backend/app/services/timeline.py`.
- Current Web API methods live in `ui/src/composables/useApi.js`.
- Current page logic lives in `ui/src/pages/NotesPage.vue`.
- Current feature registry lives in `backend/app/features.py` and its HTTP routes live in `backend/app/api/features.py`.
- Current CLI lives in `tools/chronicle_cli.py` and generated Web types live in `ui/src/types/api.generated.d.ts`.
- The selected planning playbook is `vendor/pstack/skills/poteto-mode/playbooks/multi-phase-plan.md`.
- The stack execution playbook is `vendor/pstack/skills/poteto-mode/playbooks/autopilot-stack.md`.
- The plan check is `vendor/pstack/skills/poteto-mode/scripts/check-plan.mjs`.
- Test changes follow `.agents/skills/test-audit/SKILL.md`.
