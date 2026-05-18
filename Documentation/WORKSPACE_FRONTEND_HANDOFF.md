# Conversation IDE Workspace — Frontend Handoff

Backend is complete and live. This doc is everything the frontend needs to wire the IDE panel into the existing chat UI (`AnalystDevelopmentFrontend`, Next.js 16 / React 19).

## 1. Backend contracts

All routes are mounted under `/workspace`. Auth is the same bearer token used everywhere else (`Authorization: Bearer <jwt>` → `get_current_user_id`). Replace `${API}` with the backend base URL.

### Endpoints

| Method | URL | Body | Returns |
|---|---|---|---|
| `GET`    | `${API}/workspace/{conversation_id}/files` | — | `WorkspaceFileSummary[]` (no content) |
| `GET`    | `${API}/workspace/{conversation_id}/files/{filename}` | — | `WorkspaceFile` (with content) |
| `PUT`    | `${API}/workspace/{conversation_id}/files/{filename}` | `WorkspaceWriteRequest` | `WorkspaceFile` |
| `DELETE` | `${API}/workspace/{conversation_id}/files/{filename}` | — | `{ removed: boolean, filename: string }` |
| `POST`   | `${API}/workspace/{conversation_id}/files/{filename}/execute` | — | `WorkspaceExecuteResponse` |
| `GET`    | `${API}/workspace/{conversation_id}/files/{filename}/execute/stream` | — | `text/event-stream` (SSE) |

### Type definitions (TypeScript, paste into `src/lib/api/workspace.ts`)

```ts
export type WorkspaceLanguage =
  | "python" | "javascript" | "typescript"
  | "afl"    | "sql"        | "json"
  | "yaml"   | "markdown"   | "text";

export interface WorkspaceFileSummary {
  id:           string | null;
  filename:     string;
  language:     WorkspaceLanguage;
  version:      number;
  last_author:  "agent" | "user" | "system";
  created_at:   string | null;
  updated_at:   string | null;
  size_bytes:   number;
}

export interface WorkspaceFile extends WorkspaceFileSummary {
  content:         string;
  conversation_id: string | null;
}

export interface WorkspaceWriteRequest {
  content:  string;
  language?: WorkspaceLanguage;
  author?:  "user" | "agent" | "system";    // default "user" from the IDE
}

export interface WorkspaceExecuteResponse {
  success:           boolean;
  filename:          string;
  language:          WorkspaceLanguage;
  output?:           string;
  error?:            string;
  exit_code?:        number | null;
  artifacts?:        unknown[];
  execution_time_ms?: number | null;
}

// SSE frame shapes
export type WorkspaceStreamEvent =
  | { event: "start";  data: { filename: string; language: string } }
  | { event: "stdout"; data: { text: string } }
  | { event: "stderr"; data: { text: string } }
  | { event: "end";    data: { success: boolean; exit_code: number | null;
                              execution_time_ms: number | null; artifacts: unknown[] } }
  | { event: "error";  data: { message: string } };
```

### API client (paste into `src/lib/api/workspace.ts` next to types)

```ts
import { authedFetch } from "@/lib/api/auth";   // existing helper that adds Authorization

const enc = encodeURIComponent;

export async function listWorkspaceFiles(
  conversationId: string
): Promise<WorkspaceFileSummary[]> {
  const r = await authedFetch(`/workspace/${enc(conversationId)}/files`);
  if (!r.ok) throw new Error(`list failed: ${r.status}`);
  return r.json();
}

export async function readWorkspaceFile(
  conversationId: string,
  filename: string
): Promise<WorkspaceFile | null> {
  const r = await authedFetch(
    `/workspace/${enc(conversationId)}/files/${enc(filename)}`
  );
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`read failed: ${r.status}`);
  return r.json();
}

export async function writeWorkspaceFile(
  conversationId: string,
  filename: string,
  body: WorkspaceWriteRequest
): Promise<WorkspaceFile> {
  const r = await authedFetch(
    `/workspace/${enc(conversationId)}/files/${enc(filename)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );
  if (!r.ok) throw new Error(`write failed: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function deleteWorkspaceFile(
  conversationId: string,
  filename: string
): Promise<boolean> {
  const r = await authedFetch(
    `/workspace/${enc(conversationId)}/files/${enc(filename)}`,
    { method: "DELETE" }
  );
  if (!r.ok) throw new Error(`delete failed: ${r.status}`);
  const j = await r.json();
  return !!j.removed;
}

export async function executeWorkspaceFile(
  conversationId: string,
  filename: string
): Promise<WorkspaceExecuteResponse> {
  const r = await authedFetch(
    `/workspace/${enc(conversationId)}/files/${enc(filename)}/execute`,
    { method: "POST" }
  );
  if (!r.ok) throw new Error(`execute failed: ${r.status}`);
  return r.json();
}

/**
 * SSE execution. Caller supplies handlers for each event; returns a cancel fn.
 *
 * EventSource cannot set the Authorization header, so the backend accepts the
 * JWT via `?token=...` query param on this endpoint specifically. Get the
 * current bearer token from your auth store and pass it in.
 *
 * stdout/stderr are line-buffered with a 50 ms idle flush, so prints from a
 * long-running script arrive as they happen — the IDE console feels live.
 */
export function streamExecuteWorkspaceFile(
  conversationId: string,
  filename: string,
  bearerToken: string,           // the JWT from your auth store
  handlers: {
    onStart?:  (d: { filename: string; language: string }) => void;
    onStdout?: (d: { text: string }) => void;
    onStderr?: (d: { text: string }) => void;
    onEnd?:    (d: { success: boolean; exit_code: number | null;
                     execution_time_ms: number | null; timed_out: boolean }) => void;
    onError?:  (d: { message: string }) => void;
  }
): () => void {
  const tokenParam = `?token=${enc(bearerToken)}`;
  const url =
    `/workspace/${enc(conversationId)}/files/${enc(filename)}/execute/stream` +
    tokenParam;
  const es = new EventSource(url);
  es.addEventListener("start",  (e) => handlers.onStart?.(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("stdout", (e) => handlers.onStdout?.(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("stderr", (e) => handlers.onStderr?.(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("end",    (e) => { handlers.onEnd?.(JSON.parse((e as MessageEvent).data)); es.close(); });
  es.addEventListener("error",  (e) => { try { handlers.onError?.(JSON.parse((e as MessageEvent).data)); } catch {} es.close(); });
  return () => es.close();
}
```

### Streaming semantics (Python)

- The streaming sandbox is a separate, leaner runner than the synchronous one (`core/sandbox/streaming_sandbox.py`). It's used ONLY for SSE — the JSON `POST .../execute` endpoint still goes through the main `PythonSandbox` and gets its matplotlib / plotly / file-artifact capture.
- Chunks arrive as the script writes them. Buffer flush triggers: any `\n`, ≥1024 chars buffered, or 50 ms idle.
- `print(msg)` → stdout queue. `print(msg, file=sys.stderr)` → stderr queue. Tracebacks from unhandled exceptions → stderr queue.
- Direct `sys.stdout.write(...)` calls in user code do NOT route into the queue — they hit the real process stdout. Tell the agent (and any users writing in the panel) to use `print()`. This is intentional: a global `sys.stdout` swap would let a runaway script that times out leave the FastAPI process's stdout hijacked permanently.
- Default execution cap is **60 s** (override with `SANDBOX_STREAM_TIMEOUT_S` env var). On timeout the final `end` event carries `timed_out: true`, `exit_code: 124`, and a `[execution exceeded Ns timeout]` line on stderr. The runaway thread leaks as a daemon — it gets cleaned up on process restart.
- Per-conversation persistence works the same as the synchronous path: `open('foo.txt', 'w')` lands in `$SANDBOX_HOME/conversations/{conversation_id}/`, and a later `open('foo.txt')` (in any subsequent run for the same conversation) reads it back.

## 2. Live update channel — how the panel learns about agent writes

Two options; pick **A**:

**A. Refetch on tool-result event (recommended).** The chat stream already emits a `tool_result` part for every agent tool call. In the existing chat hook, when `tool.name` starts with `workspace_`, call `listWorkspaceFiles(conversationId)` and merge into local state. No new backend transport, no race conditions. The tool result payload already contains the updated file row for write/execute calls — you can apply it optimistically before the refetch returns.

**B. WebSocket push.** Skip unless A turns out to lag visibly.

The tool-result payload shapes for the four workspace tools:

```ts
// workspace_list_files
{ success: true, tool: "workspace_list_files",
  file_count: number, files: WorkspaceFileSummary[] }

// workspace_read_file
{ success: true, tool: "workspace_read_file", file: WorkspaceFile }

// workspace_write_file
{ success: true, tool: "workspace_write_file",
  file: WorkspaceFile,
  genui_card: { type: "data-card_workspace_file",
                data: { filename, language, version, size_bytes, summary } } }

// workspace_execute_file
{ success: boolean, tool: "workspace_execute_file",
  filename: string, language: "python"|"javascript",
  output: string, error: string,
  exit_code?: number, artifacts?: any[], execution_time_ms?: number }
```

### Auto-save mirror on `execute_python`

Every non-trivial `execute_python` call also drops the executed source into the
workspace automatically (`last_author: "system"`). The user doesn't have to
ask, and the agent doesn't have to remember `workspace_write_file` for ad-hoc
analyses. The tool result carries a `workspace_file` field when this happened:

```ts
// execute_python (auto-save case)
{ success: true, tool: "execute_python",
  output: "<the actual computed output the user wanted>",
  // ... other normal execute_python fields ...
  workspace_file?: {
    filename:    string;        // slug of `description`, or auto_<hash>.py
    version:     number;
    language:    "python";
    size_bytes:  number;
    last_author: "system";
    auto_saved:  true;
  }
}
```

Skip rules (auto-save does NOT fire):
- code is empty or a true one-liner (< 80 source chars AND no newlines)
- no chat context (e.g. tool invoked from a non-authenticated path)
- workspace DB write fails (best-effort — the execute response is preserved)

## 3. UI components to build

### `WorkspacePanel` — the right-side resizable IDE pane

Location: `src/components/chat/workspace/WorkspacePanel.tsx`. Mount inside the chat layout, sibling to the message thread.

Visibility rule: render only when `files.length > 0`. The panel pops in automatically the first time the agent writes a file; the user can collapse but not destroy it.

Layout (top-to-bottom):
1. **File tab bar** (horizontal scroll). One tab per file from `listWorkspaceFiles`. Active tab is highlighted. Right-click → "Delete file" → calls `deleteWorkspaceFile`.
2. **Monaco editor**. Full content, language inferred from `file.language`. On `editor.onDidChangeModelContent` with debounce (500 ms), call `writeWorkspaceFile(..., { content, author: "user" })`. Track per-file dirty state for indicator.
3. **Toolbar above console**: `▶ Run` button (disabled if language ∉ {python, javascript}), `⟳ Reset` (reverts to last server version), `⤓ Download`.
4. **Output console** (read-only). Streams from `executeWorkspaceFile` (or the SSE variant once auth is sorted). Render stdout in default, stderr in red, exit code + duration in footer.

Layout suggestion using your existing `react-resizable-panels` install (already present in the FE):

```tsx
<PanelGroup direction="horizontal">
  <Panel defaultSize={60}><ChatThread /></Panel>
  {files.length > 0 && (
    <>
      <PanelResizeHandle />
      <Panel defaultSize={40} minSize={25}>
        <WorkspacePanel conversationId={conversationId} />
      </Panel>
    </>
  )}
</PanelGroup>
```

### `MonacoEditor` wrapper

Use `@monaco-editor/react` (npm install `@monaco-editor/react monaco-editor`). Wire `value`, `language`, `onChange`. The package handles loader caching; you don't need to self-host.

```tsx
import dynamic from "next/dynamic";
const Monaco = dynamic(
  () => import("@monaco-editor/react").then(m => m.default),
  { ssr: false }
);

<Monaco
  height="100%"
  language={file.language === "afl" ? "javascript" : file.language}   // afl gets JS-ish hl
  value={file.content}
  onChange={(v) => onChange(v ?? "")}
  options={{ minimap: { enabled: false }, fontSize: 13, wordWrap: "on" }}
  theme="vs-dark"
/>
```

### State management

Add a Zustand store (you already use Zustand) `useWorkspaceStore` keyed by `conversationId`:

```ts
interface WorkspaceState {
  files: Record<string /*conversationId*/, WorkspaceFileSummary[]>;
  activeFile: Record<string /*conversationId*/, string /*filename*/ | null>;
  contents: Record<string /*key=convId+filename*/, string>;
  dirty:   Record<string /*key*/, boolean>;
  output:  Record<string /*key*/, { stdout: string; stderr: string; status: "idle"|"running"|"done"|"error" }>;
  // actions
  loadFiles:      (conversationId: string) => Promise<void>;
  openFile:       (conversationId: string, filename: string) => Promise<void>;
  setContent:     (conversationId: string, filename: string, content: string) => void;
  saveDebounced:  (conversationId: string, filename: string) => void;
  run:            (conversationId: string, filename: string) => Promise<void>;
  delete:         (conversationId: string, filename: string) => Promise<void>;
}
```

`saveDebounced` and the auto-load on first message-with-workspace-tool-result are the only fiddly bits.

## 4. Hooking the chat stream

In your existing chat hook (probably `src/hooks/useChat.ts` or similar), watch for tool-result parts that touched the workspace — either an explicit `workspace_*` tool or an `execute_python` call that auto-saved:

```ts
function touchesWorkspace(part: ToolResultPart): boolean {
  if (typeof part.toolName !== "string") return false;
  if (part.toolName.startsWith("workspace_")) return true;
  // execute_python's auto-mirror surfaces a `workspace_file` field
  // on the result payload when the code was substantive enough to save.
  if (part.toolName === "execute_python") {
    const r = part.result as { workspace_file?: unknown } | undefined;
    return !!r && !!r.workspace_file;
  }
  return false;
}

if (part.type === "tool-result" && touchesWorkspace(part)) {
  // Refetch the file list; the panel will rerender from store.
  useWorkspaceStore.getState().loadFiles(conversationId);
}
```

That single hook keeps the panel live whether the agent went through `workspace_write_file` directly OR just ran an `execute_python` analysis that got auto-mirrored.

## 5. Run the migration

Before deploying:

```sql
-- supabase psql
\i db/migrations/034_workspace_files.sql
```

Or paste the file into the Supabase SQL editor and run. The table uses `ON DELETE CASCADE` from `conversations(id)` and `user_profiles(id)`, so deleting a conversation cleans up its files automatically.

## 6. Test path end-to-end

1. Open a new chat.
2. Ask: *"Write a Python script that prints the first 20 Fibonacci numbers, save it as `fib.py`."*
3. Agent should call `workspace_write_file({ filename: "fib.py", content: "...", language: "python" })`.
4. Panel should pop in with `fib.py` as the active tab.
5. Click ▶ Run. Console should show `1 1 2 3 5 ...`.
6. Edit the file in the panel (change limit to 5). Save indicator → "saved".
7. Ask: *"Add a sum at the bottom."* Agent should `workspace_read_file` first (to see your edit), then `workspace_write_file` with the new version.
8. Refresh the page → panel + content survive.
9. Delete the conversation → row in `workspace_files` is gone (FK cascade).

## 7. What's not wired yet (open follow-ups)

- ~~**SSE auth.**~~ ✅ Done. The stream route accepts the JWT via `?token=…` query param (`get_current_user_id_sse` in `api/dependencies.py`). The `Authorization` header still wins when both are present; query param is the EventSource path.
- ~~**Python output is captured-then-returned, not chunk-streamed.**~~ ✅ Done. The SSE route now goes through `core/sandbox/streaming_sandbox.py` which line-buffers stdout/stderr and pushes chunks through an `asyncio.Queue` as the script writes them.
- **JS streaming.** Still synchronous through `node` subprocess. The SSE wire format already accommodates chunked stdout, but the `_execute_javascript` helper in `core/workspace.py` doesn't stream yet — a future patch can swap `subprocess.run` for `asyncio.create_subprocess_exec` and pipe stdout lines into the same queue.
- **Read-only viewer for non-executable languages** (afl, sql, json, markdown) — same panel, just hide the ▶ Run button when `language ∉ {python, javascript}`.
- **Token rotation.** Because the JWT appears in the SSE URL, treat the panel's stream URL as sensitive: don't log it client-side, don't write it to local storage, and re-establish the EventSource when the user's token refreshes (`onerror` from `EventSource` after a 401 is your cue).
- **Long-running thread leak on timeout.** When a script blows past `SANDBOX_STREAM_TIMEOUT_S` (default 60 s) the daemon thread keeps running until the FastAPI process restarts. Practically harmless (no CPU work happens after the user navigates away in most cases), but if you find users repeatedly triggering timeouts, consider running the streaming sandbox via `multiprocessing` so a SIGTERM is available.
