# CLAUDE.md

## Project Overview

全息拉普拉斯互联网爬虫系统 - Multi-platform web crawler with visual UI.
Backend: Flask (Python 3.11). Frontend: Vanilla JS + Bootstrap 5. Deployment: Docker + Nginx.

## Project Structure

```
backend/
  crawler.py          # All crawler classes + data processing (~4300 lines)
  crawler_server.py   # Flask API server + route handlers (~3300 lines)
  requirements.txt
  tasks.json          # Runtime task persistence (do not commit with task data)

frontend/
  index.html          # Single page app
  script.js           # Main UI logic (~5600 lines)
  api_client.js       # API client (ApiClient object)
  ui-manager.js       # UI component management
  language-manager.js # i18n
  styles.css
  css/                # Theme, background, live2d styles
  js/                 # Ad, background, theme, live2d managers

docs/                 # GitHub Pages mirror of frontend/ (keep in sync)
```

## Key Classes (backend/crawler.py)

- `WebCrawler` (line ~124) - Generic web crawler
- `WikipediaAPICrawler` (line ~919) - Wikipedia API
- `ZhihuZhuanlanCrawler` (line ~1238) - Zhihu
- `MoegirlCrawler` (line ~1525) - Moegirl wiki
- `BilibiliCrawler` (line ~1600) - Bilibili
- `GitHubCrawler` (line ~1711) - GitHub
- `WeiboCrawler` (line ~1806) - Weibo
- `YouTubeCrawler` (line ~1907) - YouTube
- `TiebaCrawler` (line ~2022) - Baidu Tieba
- `ArxivCrawler` (line ~2115) - arXiv papers
- `DocsCrawler` (line ~2223) - Generic docs
- `CrawlerHub` (line ~2315) - Unified dispatcher for all crawlers
- `DataProcessor` (line ~2563) - NLP, keyword extraction, TF-IDF
- `StorageManager` (line ~3044) - Result file I/O
- `UrbanLegendAnalyzer` (line ~3211) - Conspiracy detection

## Critical Rules

### General
- This project uses Chinese comments and log messages. Follow existing style.
- No database. All persistence is via tasks.json and file system.
- JSON encoding uses `NumpyEncoder` for NumPy types. Always use it when serializing results.

### Backend
- All API routes are in `crawler_server.py`, prefixed with `/api/`.
- Each platform crawler has its own factory function (e.g., `get_wiki_crawler()`).
- Tasks run in background threads via `ThreadPoolExecutor`.
- Always call `save_tasks()` after modifying `tasks` or `wiki_tasks` dicts.
- Flask app uses `CORS(app)` - do not add per-route CORS decorators.
- File uploads limited to 16MB (`MAX_CONTENT_LENGTH`).
- Use `logger` (not `print`) for all backend logging.

### Frontend
- No build step. Plain JS, no bundler, no npm.
- `ApiClient` in `api_client.js` is the single point for all API calls.
- `API_BASE_URL` is configurable via localStorage for GitHub Pages deployment.
- Chart.js and ECharts are loaded via CDN in index.html.
- All DOM manipulation happens inside `DOMContentLoaded` callback in script.js.

### When Modifying Code
- If you change a function signature, update ALL callers in the same commit.
- If you add a new API route in crawler_server.py, also add the corresponding method in frontend/api_client.js.
- If you modify frontend/, mirror the same changes to docs/ (GitHub Pages).
- If you add a new crawler class, register it in CrawlerHub and add its routes in crawler_server.py.
- If you change CSS class names, search both .html and .js files for usage.

### Testing & Verification
- Backend: `cd backend && python -c "from crawler import *; from crawler_server import app; print('OK')"` to verify imports.
- Frontend: Open index.html in browser, no build needed.
- Docker: `docker-compose up --build` to test full stack.
- Health check endpoint: `GET /health` should return 200.

## Common Patterns

### Adding a new API endpoint
1. Add route function in `crawler_server.py`
2. Add corresponding `ApiClient` method in `frontend/api_client.js`
3. Copy updated `api_client.js` to `docs/api_client.js`
4. Add UI trigger in `frontend/script.js` if needed

### Adding a new crawler
1. Create class in `backend/crawler.py` following existing pattern (inherit structure)
2. Add to imports in `crawler_server.py` (line ~21)
3. Register in `CrawlerHub` class
4. Add API routes in `crawler_server.py`
5. Add mock endpoints if needed

## Code Completion Checklist (MANDATORY)

Every time you finish writing or modifying code, you MUST run through this checklist BEFORE telling the user you are done. Do NOT skip any item. These are real bugs that have occurred repeatedly in this project.

### 1. Phantom Endpoint Check (虚空端点)
- Every `fetch()` or API call in frontend JS → verify the route ACTUALLY EXISTS in `crawler_server.py` by reading the file. Do not assume. Do not guess from memory.
- Every `ApiClient` method → verify it calls a real backend route.
- If you wrote a new frontend feature that calls `/api/xxx`, open `crawler_server.py` and confirm `@app.route('/api/xxx')` exists. If it doesn't, create it.

### 2. Parameter Contract Check (参数契约)
- For every API call: verify the request parameter names match EXACTLY between frontend (what is sent) and backend (what is read via `request.args` / `request.json`).
- For third-party APIs (Wikipedia, Bilibili, etc.): READ THE ACTUAL DOCS or existing working code. Do not guess parameter behavior. Boolean-like flags (e.g., Wikipedia `exintro`) may activate by presence, not by value.
- If backend expects `title` but frontend sends `url`, that is a bug. Fix it.

### 3. Cross-File Consistency Check (跨文件一致性)
- Changed a function signature → `grep` for ALL callers across the entire project and update every one.
- Changed a backend route path → search `frontend/`, `docs/`, and `api_client.js` for the old path.
- Added/removed a CSS class → search `.html`, `.js`, and `.css` files.
- Changed `api_client.js` → copy to `docs/api_client.js`.
- Changed any file in `frontend/` → mirror to `docs/`.

### 4. UI State Management Check (状态管理)
- Every button/action that triggers an async operation:
  - MUST disable itself or show loading state during the operation.
  - MUST re-enable or reset state when the operation completes OR fails.
  - Clicking the same button twice must not break anything (idempotency).
- Every loading indicator MUST have a corresponding hide/clear on both success AND error paths.

### 5. Error & Edge Case Check (错误处理)
- Every `fetch()` call → must have `.catch()` or try/catch with user-visible error feedback.
- Network timeout → show a message to the user with option to retry. Never silently hang.
- Empty results → show "no results found" message, not a blank screen.
- API returns error status → display the error, do not ignore it.

### 6. Completeness Check (完整性)
- Re-read the user's original request. Count how many things they asked for. Verify you addressed ALL of them, not just the first one.
- If the task has N steps, verify you completed N steps, not N-1.

### 7. Security Check (安全检查)
- NEVER use `innerHTML` with any data that originates from user input or API responses. Use `textContent` or create elements with `createElement()`.
- NEVER put API keys, tokens, or credentials in frontend code.
- All user input displayed on page must be escaped. If using `innerHTML` for formatting, sanitize first.
- Backend must validate all input from `request.args` / `request.json`. Do not trust frontend validation alone.
- Use parameterized queries if any database interaction is ever added. Never concatenate user input into queries.

### 8. Response Format Consistency (响应格式一致性)
- All API success responses MUST use the same structure: `{"success": true, "data": ...}` or return data directly — pick ONE pattern and stick to it across ALL endpoints.
- All API error responses MUST use: `{"error": "message"}` with appropriate HTTP status code (400 for bad input, 404 for not found, 500 for server error). Do not return 200 with error in body.
- Field naming convention: use `snake_case` in Python backend, use `camelCase` in JS frontend. If conversion is needed, do it in ONE place (ApiClient), not scattered everywhere.

### 9. Async & Promise Handling (异步处理)
- Every `fetch()` chain MUST have `.catch()`. Every `async` function MUST have `try/catch`.
- Check `response.ok` before calling `response.json()`. A 404 response is not JSON — calling `.json()` on it will throw.
- If multiple async operations update the same DOM element or state, ensure ordering. Use a request ID or abort previous requests with `AbortController`.
- Never fire-and-forget: `fetch('/api/something')` without await or `.then()` is always a bug.

### 10. DOM & Memory (DOM 与内存)
- Every `addEventListener()` on dynamically created elements must have a corresponding cleanup path, or use event delegation on a parent element instead.
- Never use `innerHTML +=` in a loop — it re-parses the entire content each time. Build the string first, then assign once, or use `DocumentFragment`.
- `setInterval()` and `setTimeout()` must be tracked and cleared when no longer needed. Store the ID and call `clearInterval()`/`clearTimeout()`.
- Avoid caching DOM references to elements that may be removed and re-created.

### 11. CSS & Layout (样式与布局)
- Never use hardcoded `px` widths on containers that should be responsive. Use `max-width`, `%`, or `min()`/`clamp()`.
- If you add `z-index`, check existing z-index values in the project first. Do not blindly use `9999`.
- `overflow: hidden` hides content — only use it when you are certain nothing will be clipped. Prefer `overflow: auto` for scrollable areas.
- Every `position: absolute` or `position: fixed` element needs an explicit `z-index` and a positioned parent (`position: relative` on container).
- If you change a class name in CSS, grep for it in ALL `.html`, `.js` files. CSS class renames break silently.

### 12. Data Shape & Type Safety (数据类型)
- When receiving JSON from backend, always handle: missing fields (`undefined`), `null` values, empty arrays `[]`, and empty strings `""`. Do not assume data is always present and well-formed.
- Number fields from JSON may arrive as strings (e.g., query params are always strings). Parse explicitly with `parseInt()`/`parseFloat()` where needed.
- Python `None` becomes JSON `null` becomes JS `null`. Python `True/False` becomes `true/false`. Do not compare with `==` to string `"true"`.
- When passing data between frontend and backend, verify types match: JS `number` vs Python `int`/`float`, JS `array` vs Python `list`, JS `object` vs Python `dict`.

### Self-Verification Command
After completing code changes, run:
```bash
cd backend && python -c "from crawler import *; from crawler_server import app; print('OK')"
```
If this fails, fix it before declaring the task done.

## Do Not
- Do not introduce npm, webpack, or any JS build tooling.
- Do not replace file-based storage with a database without explicit request.
- Do not modify tasks.json schema without updating both load_tasks() and save_tasks().
- Do not add Python dependencies without adding them to requirements.txt.
- Do not forget to sync frontend/ changes to docs/.
