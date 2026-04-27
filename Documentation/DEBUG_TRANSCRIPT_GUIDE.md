# Debug Transcript System — Complete Guide

## Overview

The Debug Transcript system captures **every step of every backend process** when a user sends a message. It records system prompts, full message history, every streamed text token, every tool call (name + input + output), every sandbox/Node.js execution (code + stdout/stderr + exit code), skill invocations, per-iteration token usage, and the final response — all written to disk as both JSON and human-readable `.txt` files.

**Zero-cost when disabled.** All hooks are guarded with `if _dt:` so when `DEBUG_TRANSCRIPTS_ENABLED` is not set to `1`, there is absolutely no performance impact.

---

## Enabling Debug Transcripts

Set the environment variable:

```
DEBUG_TRANSCRIPTS_ENABLED=1
```

On Railway: go to your service → Variables → add `DEBUG_TRANSCRIPTS_ENABLED` = `1`.

Transcripts are stored under `$STORAGE_ROOT/debug_transcripts/<user_id>/<conversation_id>/<request_id>.{json,txt}`.

---

## What Gets Captured

| Event | Description |
|---|---|
| `request` | HTTP method, path, model, user content, skill slug |
| `model_resolved` | The final model string sent to the provider |
| `system_prompt` | Full system prompt text (potentially 10k+ tokens) |
| `messages` | Full message array passed to the LLM after context management |
| `text_delta` | Every streamed text chunk from the LLM (buffered, flushed at 300 chars or end) |
| `tool_call_start` | Tool name + full JSON input, recorded when the LLM invokes a tool |
| `tool_call_end` | Tool name + full JSON output + duration ms, recorded after the tool returns |
| `sandbox_exec` | Language, full code, stdout, stderr, exit code, duration ms |
| `skill_invocation` | Skill slug + input context (when skills are invoked) |
| `iteration` | Iteration number, duration ms, token usage for that iteration |
| `final_response` | Accumulated content, tools used list, total token usage, iteration count |
| `error` | Exception type + message for any error path |

---

## API Endpoints

All endpoints live under the `/debug` prefix and require a valid `Authorization: Bearer <token>` header (same auth as all other routes).

### Check Status

```
GET /debug/status
```

Returns whether debug transcripts are enabled and the storage path.

**Response:**
```json
{
  "enabled": true,
  "storage_root": "/data/debug_transcripts",
  "message": "Debug transcripts are ENABLED"
}
```

---

### List Transcripts

```
GET /debug/transcripts?user_id=<uid>&conversation_id=<cid>&limit=20
```

All query params are optional. Without `user_id`, lists the most recent transcripts across all users. Without `conversation_id`, lists all conversations for the user.

**Response:**
```json
{
  "transcripts": [
    {
      "request_id": "req_abc123",
      "user_id": "user_xyz",
      "conversation_id": "conv_456",
      "started_at": "2026-04-27T10:30:00Z",
      "finished_at": "2026-04-27T10:30:12Z",
      "duration_ms": 12340,
      "model": "claude-opus-4-5",
      "event_count": 47,
      "has_error": false,
      "json_path": "/data/debug_transcripts/...",
      "txt_path": "/data/debug_transcripts/..."
    }
  ],
  "count": 1
}
```

---

### Get Transcript (JSON)

```
GET /debug/transcripts/<request_id>
```

Returns the full machine-readable JSON transcript for a specific request.

---

### Get Transcript (Human-readable Text)

```
GET /debug/transcripts/<request_id>/text
```

Returns the human-readable `.txt` transcript. **This is the most useful endpoint for debugging.** It shows every event in a clean, formatted layout.

**Example output snippet:**
```
============================================================
DEBUG TRANSCRIPT
Request ID : req_abc123_20260427_103000
User       : user_xyz
Conversation: conv_456
Started    : 2026-04-27T10:30:00.123456
============================================================

[10:30:00.123] REQUEST
  Method: POST /chat/agent
  Model requested: claude-opus-4-5
  Skill: potomac-pptx
  Content: Create a PowerPoint about the missing days narrative

[10:30:00.145] MODEL_RESOLVED
  Model: claude-opus-4-5-20251101

[10:30:00.201] SYSTEM_PROMPT (4231 chars)
  You are Yang, an intelligent financial AI assistant...

[10:30:00.210] MESSAGES (3 messages)
  [0] system: (4231 chars)
  [1] user: Create a PowerPoint about...
  [2] assistant: (previous turn)

[10:30:01.500] TEXT_DELTA
  Sure! Let me create that presentation for you.

[10:30:01.750] TOOL_CALL_START
  Tool: run_javascript_sandbox
  Input:
  {
    "code": "const pptx = require('pptxgenjs')...",
    ...
  }

[10:30:08.200] TOOL_CALL_END
  Tool: run_javascript_sandbox  (6450.00 ms)
  Output:
  {
    "success": true,
    "stdout": "Slide 1 created...",
    ...
  }

[10:30:08.250] SANDBOX_EXEC  [nodejs]  (6200.00 ms)
  Code (1823 chars):
  const pptx = require('pptxgenjs');
  ...
  STDOUT:
  Slide 1 created
  Slide 2 created
  STDERR: (none)
  Exit Code: 0

[10:30:09.100] ITERATION 1  (9000.00 ms)
  Input tokens : 4521
  Output tokens: 312
  Total tokens : 4833

[10:30:09.200] FINAL RESPONSE
  Iterations  : 1
  Total tokens: 4833
  Tools used  : run_javascript_sandbox
  Content (45 chars):
  Your presentation is ready for download...

============================================================
FINISHED: 2026-04-27T10:30:09.200000  (duration: 9077.00 ms)
============================================================
```

---

### Download Transcript

```
GET /debug/transcripts/<request_id>/download
```

Downloads the `.txt` file directly with `Content-Disposition: attachment`.

---

### Delete a Transcript

```
DELETE /debug/transcripts/<request_id>
```

Deletes both the `.json` and `.txt` files for a single request.

---

### Delete All Transcripts

```
DELETE /debug/transcripts?user_id=<uid>&conversation_id=<cid>
```

Deletes all transcripts. Optionally scope by `user_id` and/or `conversation_id`.

---

### Prune Old Transcripts

```
POST /debug/transcripts/prune
Content-Type: application/json

{ "max_age_days": 7 }
```

Deletes transcripts older than `max_age_days` (default: 7 days). Returns a count of deleted files.

---

## Typical Debugging Workflow

### Debugging a PowerPoint Issue

1. **Enable transcripts** — set `DEBUG_TRANSCRIPTS_ENABLED=1` on Railway and redeploy (or it takes effect immediately if using env vars without redeploy).

2. **Reproduce the issue** — send the exact message that produces bad output (e.g., blank slide 1).

3. **Find your transcript:**
   ```
   GET /debug/transcripts?conversation_id=<your_conv_id>
   ```

4. **Read the human-readable version:**
   ```
   GET /debug/transcripts/<request_id>/text
   ```

5. **Look for:**
   - `SANDBOX_EXEC` — did the Node.js code produce an error in stderr?
   - `TOOL_CALL_END` — did the tool return an error?
   - `TEXT_DELTA` — what exactly did Claude say before calling the tool?
   - `MESSAGES` — is the message history being fed correctly?
   - `SYSTEM_PROMPT` — is the Potomac PPTX skill prompt being injected?

### Common Issues to Check

| Symptom | Where to look |
|---|---|
| Blank slide 1 | `SANDBOX_EXEC` stdout — check if slide 1 content was written |
| Tool not called | `TEXT_DELTA` — Claude may have responded in plain text instead |
| Wrong model used | `MODEL_RESOLVED` — compare to what you expected |
| Skill not loaded | `SYSTEM_PROMPT` — skill instructions should appear in the prompt |
| Truncated context | `MESSAGES` — check total messages count and content length |
| Node.js crash | `SANDBOX_EXEC` stderr + exit code |

---

## Architecture

### Core Module: `core/debug_transcript.py`

- **`DebugTranscript`** class — holds the event list, writes files
- **`_current_transcript`** — `contextvars.ContextVar` that propagates through `asyncio.to_thread` automatically (no function signature changes needed)
- **Thread-safe** — event list protected by `threading.Lock`
- **Text buffering** — text deltas buffered and flushed at 300 chars to avoid thousands of tiny entries

### Instrumented Files

| File | What's hooked |
|---|---|
| `api/routes/chat.py` | Request, model resolved, system prompt, messages, text deltas, tool call starts, iteration stats, final response, error handlers |
| `core/tools.py` | Tool call end (success + exception paths) |
| `core/sandbox/manager.py` | Sandbox execution (code + stdout/stderr + exit code) |

### Storage Layout

```
$STORAGE_ROOT/
  debug_transcripts/
    <user_id>/
      <conversation_id>/
        <request_id>.json   ← machine-readable
        <request_id>.txt    ← human-readable
```

`STORAGE_ROOT` defaults to `/data` (Railway volume) or the current directory if not set.

---

## Security Notes

- All debug endpoints require the same Bearer token authentication as all other API routes.
- Transcripts contain **full message content including user data** — treat them as sensitive.
- Use `DELETE /debug/transcripts` or the prune endpoint to clean up after debugging sessions.
- Consider disabling `DEBUG_TRANSCRIPTS_ENABLED` in production once debugging is complete.
- Storage can grow large if left enabled — each transcript can be 50–500 KB depending on tool usage.

---

## Performance Impact

- **Disabled (`DEBUG_TRANSCRIPTS_ENABLED` not set or `0`):** Zero overhead. All hooks are `if _dt:` guarded and the `ContextVar` is never set.
- **Enabled:** Minimal overhead from JSON serialization of tool inputs/outputs and file I/O at request end. The file write is synchronous but happens after the streaming response has finished. Text deltas are buffered (flushed every 300 chars) to avoid excessive entries.
