# 视觉 QA · 2026-07-07 · loading performance

- Task: `docs/loading-performance-design.md` 第一轮代码落地后的中栏虚拟化、右栏缓存/取消、移动端滚动恢复回归。
- Desktop fixture: `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- Large topic smoke: `http://127.0.0.1:8798/?topic=4&mode=view`
- Mobile fixture: `http://127.0.0.1:8798/?topic=1&mode=view`
- Viewports:
  - Desktop: `1920x1080`
  - Mobile: `390x844`

Commands:

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py tests/test_note_types_capabilities.py
$env:TIMELINE_BACKEND_URL='http://127.0.0.1:8010'; cmd /c npm run qa:visual-fixture
$env:TIMELINE_BACKEND_URL='http://127.0.0.1:8010'; cmd /c npm run qa:visual-server
python tools/bench_timeline_loading.py --count 5000 --base-url http://127.0.0.1:8798
python tools/bench_timeline_loading.py --cleanup
```

Artifacts:

- `1920-fixture-after.png` — fixed fixture desktop state.
- `1920-topic4-after.png` — large topic smoke on topic `4`.
- `390-mobile-list-after.png` — mobile main feed state.
- `390-mobile-detail-after.png` — mobile full-screen detail after tapping the first row.

Checks:

- Fixed fixture still resolves with `topic=1`, `event=1`, `mode=edit`.
- `topic=4` desktop state renders a long timeline without blanking the sidebar.
- Mobile main feed opens in single-column timeline mode and a row tap opens full-screen detail.
- `tools/bench_timeline_loading.py` successfully created six dedicated perf topics (`timeline/table/list/gallery/board/outline`) with `5000` events each and cleaned them afterward.

Performance evidence:

- `topic=4` timeline（desktop `1920x1080`，same browser session second navigation as warm-run）：
  - first visible row: `583.5ms`
  - DOM rows before scroll: `42`
  - DOM rows after 5s scripted scroll: `54`
  - long tasks during 5s scroll: `12`
  - max long task: `91ms`
- `zzPerfTimelineQA-timeline`（`5000` events）：
  - cold first visible row: `715.8ms`
  - warm first visible row: `350.3ms`
  - DOM rows before scroll: `42`
  - DOM rows after 5s scripted scroll: `42`
  - max long task during 5s scroll: `54ms`
- `zzPerfTimelineQA-gallery`（`5000` events）：
  - DOM cards on first paint: `11`
- `zzPerfTimelineQA-board`（`5000` events，overscan reduced to `4`）：
  - total visible cards after warm scroll sample: `57`
  - max cards in one column: `19`
  - max long task during 5s scroll: `100ms`
- Fixed fixture detail switching（desktop `1920x1080`）：
  - first row open miss: `65ms`
  - second row switch: `0.4ms`
  - cached reopen hit: `27.9ms`

Test noise:

- `cmd /c npm run test:ui` rerun after the final fixes no longer emits the previous Vue `onBeforeUnmount` warning from `usePaneSwapDrag`.

Environment notes:

- Port `8000` was already occupied by an unrelated listener before QA started and returned `404` for `/api/topics`, so this QA run used a dedicated backend on `127.0.0.1:8010`.
- Visual server for this run proxied to `http://127.0.0.1:8010` on `127.0.0.1:8798`.
- The temporary perf topics and shelf were removed after smoke verification; no permanent QA notebook was left in the local database.
