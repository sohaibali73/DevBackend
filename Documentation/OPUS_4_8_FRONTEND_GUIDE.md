# Frontend Update Guide — Claude Opus 4.8

This guide describes what the frontend needs to change to expose the newly added
**Claude Opus 4.8** model. Backend support is already complete (see
`core/claude_engine.py` and `api/routes/chat.py`).

---

## 1. The new model

| Field | Value |
|-------|-------|
| Model ID (send to API) | `claude-opus-4-8` |
| Suggested display name | `Claude Opus 4.8` |
| Max output tokens | `128000` |
| Context window | `1,000,000` |
| Extended / adaptive thinking | ✅ supported (`thinking_effort`: `low` / `medium` / `high`) |
| Prompt caching | ✅ supported |
| Tier | Latest / most capable Opus (default Opus pick) |

> The model string is the **only** required value to send. Everything else
> (token limits, thinking, caching) is resolved server-side from the model ID.

---

## 2. Add it to the model picker

Wherever the model dropdown / selector list is defined, add Opus 4.8 as the
top Opus option. Example shape:

```ts
const MODELS = [
  {
    id: "claude-opus-4-8",
    label: "Claude Opus 4.8",
    tier: "opus",
    badge: "New",            // optional UI badge
    maxOutputTokens: 128000,
    contextWindow: 1000000,
    supportsThinking: true,
  },
  { id: "claude-opus-4-7", label: "Claude Opus 4.7", tier: "opus", /* ... */ },
  { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", tier: "sonnet", /* ... */ },
  // ...existing models
];
```

If the picker is populated dynamically, you can pull it from
`GET /chat/models` — Opus 4.8 will appear in the Anthropic provider list once
the registry is refreshed.

---

## 3. Sending a chat request

No request-shape changes. Just pass the new model id in the existing
`/chat/agent` or `/chat/agent/ui-stream` payload:

```ts
await fetch("/chat/agent/ui-stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    content: userMessage,
    conversation_id: conversationId,
    model: "claude-opus-4-8",      // ← the only change
    // optional adaptive thinking:
    thinking_mode: "enabled",
    thinking_effort: "high",        // "low" | "medium" | "high"
    use_prompt_caching: true,       // default true
  }),
});
```

---

## 4. Optional: default model

If you want Opus 4.8 to be the default selection for new conversations, update
the frontend default constant (e.g. `DEFAULT_MODEL = "claude-opus-4-8"`).
The backend default remains Sonnet for the AFL engine, so this is a
frontend-only preference.

---

## 5. Checklist

- [ ] Add `claude-opus-4-8` to the model selector list with label “Claude Opus 4.8”.
- [ ] (Optional) Show a “New” badge.
- [ ] Confirm the thinking-effort toggle is enabled for this model (it supports adaptive thinking).
- [ ] (Optional) Set it as the default model.
- [ ] Smoke test: send a message with `model: "claude-opus-4-8"` and confirm a streamed response + `model_used: "claude-opus-4-8"` in the finish event.

---

## 6. Notes / gotchas

- The token limit (128k output) and context window (1M) are enforced
  server-side — the frontend does not need to clamp `max_tokens`.
- If `pin_model_version: true` is sent, the backend maps the alias to its
  pinned snapshot (currently `claude-opus-4-8` → `claude-opus-4-8`).
- Older aliases still work unchanged: `claude-opus-4-7`, `claude-opus-4-6`,
  `claude-sonnet-4-6`, etc.
