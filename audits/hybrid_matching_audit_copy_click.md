# Hybrid Matching Audit — Voice: "copy" + Gesture: "click"

**Scope:** `core/intent_resolver.py` + `config/hybrid_bindings.py`  
**Task:** Audit key formation and binding lookup for the example pair (`voice="copy"`, `gesture="click"`).  
**Code Changes:** None (read-only analysis).

---

## 1. Expected Hybrid Key Format

Per `IntentResolver.resolve_hybrid()`:

```python
key = (voice_action, gesture_type)
```

For the chosen example:

```python
("copy", "click")
```

This is a 2-element tuple where:
- `voice_action` = the spoken word / transcript ("copy")
- `gesture_type` = the gesture classifier output ("click")

---

## 2. Actual Hybrid Key Format

The same method executes exactly:

```python
key = (voice_action, gesture_type)
```

No transformation, lowercasing, or normalization is applied beyond what the caller passes in.

**Actual key produced:**

```python
("copy", "click")
```

---

## 3. HYBRID_BINDINGS Compatibility

**NO**

Current contents of `config/hybrid_bindings.py`:

```python
HYBRID_BINDINGS: dict = {
    ("open", "point"):         "open_at_cursor",
    ("search", "air_letter"):  "search_for_letter",
    ("scroll_up", "scroll_up"):   "scroll_up_fast",
    ("scroll_down", "scroll_down"): "scroll_down_fast",
    ("click", "point"):        "click_at_point",
}
```

The key `("copy", "click")` is **absent** from the dictionary.

---

## 4. Root Mismatch Reason

| Step | Observation |
|------|-------------|
| **Key formation** | Correct — `resolve_hybrid()` builds `(voice_action, gesture_type)` as expected. |
| **Binding lookup** | `("copy", "click") in self._bindings` evaluates to `False`. |
| **Root cause** | The `HYBRID_BINDINGS` config simply does not define an entry for voice action `"copy"` paired with gesture `"click"`. |

Because the key is missing, `resolve_hybrid()` returns `None`, and the hybrid pipeline falls back to voice-only execution (if triggered earlier) or gesture-only execution.

---

## Summary

| Metric | Value |
|--------|-------|
| **Expected hybrid key format** | `("copy", "click")` |
| **Actual hybrid key format** | `("copy", "click")` |
| **HYBRID_BINDINGS compatibility** | **NO** |
| **Root mismatch reason** | `HYBRID_BINDINGS` lacks the `("copy", "click")` entry; key formation logic itself is correct. |

