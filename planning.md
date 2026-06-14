# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

### Tool 1: search_listings

**What it does:**
Filters the mock listings dataset against a user's keywords, optional size, and optional price ceiling. Returns a ranked list of matching items, best match first.

**Input parameters:**
- `description` (str): Free-text keywords from the user's query (e.g., "vintage graphic tee", "leather jacket"). Used to score matches against each listing's title, description, style_tags, colors, brand, and category.
- `size` (str | None): Size string to filter by (e.g., "M", "L/XL"). Case-insensitive substring match — "M" matches "S/M" and "M/L". Pass None to skip size filtering.
- `max_price` (float | None): Maximum price in dollars, inclusive. Pass None to skip price filtering.

**What it returns:**
A list of listing dicts, sorted by relevance score (highest first). Each dict contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str|None), `platform` (str). Returns `[]` if nothing matches — never raises an exception.

Relevance scoring: for each listing that passes the price and size filters, count how many words from `description` appear in the combined text of the listing's title + description + style_tags + colors + brand. Drop listings with a score of 0. Sort by score descending.

**What happens if it fails or returns nothing:**
Returns `[]`. The planning loop checks for this immediately after the call. If the list is empty, the session's `error` field is set to: `"No listings matched your search. Try a broader description, a different size, or a higher budget."` and the agent returns early — `suggest_outfit` and `create_fit_card` are never called.

---

### Tool 2: suggest_outfit

**What it does:**
Sends the selected listing and the user's wardrobe to the LLM and returns 1–2 complete outfit suggestions as a plain string. If the wardrobe is empty, returns general styling advice for the item instead.

**Input parameters:**
- `new_item` (dict): A single listing dict (the top result from `search_listings`). The prompt uses `title`, `description`, `style_tags`, `colors`, `condition`, and `platform`.
- `wardrobe` (dict): A wardrobe dict with an `'items'` key containing a list of wardrobe item dicts. Each wardrobe item has: `name`, `category`, `colors`, `style_tags`, `notes`. May be `{'items': []}`.

**What it returns:**
A non-empty string. If the wardrobe has items: 1–2 outfit combinations using named pieces from the wardrobe. If the wardrobe is empty: general advice on what types of clothing, shoes, and accessories pair well with the item, and what vibe it suits.

Example (non-empty wardrobe): `"Pair the faded band tee with your baggy straight-leg jeans and chunky white sneakers for a classic 90s streetwear look. Throw on the vintage black denim jacket if you want a layer — tuck the front corner of the tee slightly for shape."`

**What happens if it fails or returns nothing:**
The LLM call is wrapped in a try/except. If it raises an exception, return the string: `"Couldn't generate outfit suggestions right now. Try describing your wardrobe and I can help manually."` The planning loop checks whether the returned string is non-empty before passing it to `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Sends the outfit suggestion and item details to the LLM and generates a 2–4 sentence Instagram/TikTok-style caption for the find. Uses a higher temperature (0.9) so output varies across calls.

**Input parameters:**
- `outfit` (str): The suggestion string returned by `suggest_outfit`. If empty or whitespace-only, the tool returns an error string immediately without calling the LLM.
- `new_item` (dict): The listing dict. The prompt uses `title`, `price`, `platform`, and `condition`.

**What it returns:**
A 2–4 sentence string that sounds like a real OOTD caption — lowercase, casual, mentions the item name/price/platform once each, and captures the outfit vibe in specific terms (not generic phrases like "love this look"). Different inputs must produce different outputs.

Example: `"thrifted this faded band tee off depop for $22 and it was literally made for my wide-legs 🖤 rolled the sleeves once and tucked the front corner and suddenly it's an outfit. full look in my stories"`

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace: return `"Unable to generate a fit card — outfit description was missing."` without calling the LLM. If the LLM call raises: return `"Fit card generation failed. Here's the outfit suggestion instead: {outfit}"`.

---

### Additional Tools (if any)

None for required features. See stretch features section if adding a price comparison tool.

---

## Planning Loop

The loop runs sequentially with one early-exit branch. There is no retry or backtracking in the base implementation.

```
1. Parse the query
   - Extract `description`, `size`, `max_price` from the raw query string using the LLM.
   - Store in session["parsed"] = {"description": ..., "size": ..., "max_price": ...}
   - If parsing fails: fall back to using the full query as the description, size=None, max_price=None.

2. Call search_listings(description, size, max_price)
   - Store result in session["search_results"]
   - IF result is []:
       → set session["error"] = "No listings matched your search. Try a broader description, a different size, or a higher budget."
       → RETURN session immediately (early exit)
   - ELSE:
       → set session["selected_item"] = session["search_results"][0]

3. Call suggest_outfit(session["selected_item"], session["wardrobe"])
   - Store result in session["outfit_suggestion"]
   - No early exit here — suggest_outfit always returns a non-empty string.

4. Call create_fit_card(session["outfit_suggestion"], session["selected_item"])
   - Store result in session["fit_card"]

5. Return session
```

The key conditional is at Step 2. Everything after it runs only if `search_listings` returned at least one result. The agent never calls `suggest_outfit` or `create_fit_card` with empty or None input.

---

## State Management

One `session` dict is initialized at the start of `run_agent()` and passed through every step. No global state. No re-prompting the user between steps.

Fields and when they're written:

| Field | Written at | Read by |
|-------|-----------|---------|
| `query` | init | query parser |
| `parsed` | Step 2 (parse) | search_listings call |
| `search_results` | Step 2 (search) | Step 2 early-exit check |
| `selected_item` | Step 2 (after search) | suggest_outfit, create_fit_card |
| `wardrobe` | init (passed in) | suggest_outfit |
| `outfit_suggestion` | Step 3 | create_fit_card |
| `fit_card` | Step 4 | app.py display |
| `error` | Step 2 early exit | app.py display |

`selected_item` is always `search_results[0]` — a full listing dict, not just an ID. This means `suggest_outfit` and `create_fit_card` receive all listing fields without any additional lookup.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match (returns `[]`) | Set `session["error"]` = `"No listings matched your search. Try a broader description, a different size, or a higher budget."` Return session immediately. `outfit_suggestion` and `fit_card` remain `None`. |
| `suggest_outfit` | LLM call raises an exception | Catch the exception inside the tool. Return the string `"Couldn't generate outfit suggestions right now. Try describing your wardrobe and I can help manually."` Planning loop continues — `create_fit_card` will receive this fallback string. |
| `create_fit_card` | `outfit` is empty or whitespace | Return `"Unable to generate a fit card — outfit description was missing."` immediately, no LLM call. |
| `create_fit_card` | LLM call raises an exception | Return `"Fit card generation failed. Here's the outfit suggestion instead: {outfit}"` |

---

## Architecture

```
User query (str)
    │
    ▼
┌─────────────────────────────────────────────┐
│              run_agent()                    │
│                                             │
│  1. Parse query → session["parsed"]         │
│     (LLM extracts description/size/price)   │
│                                             │
│  2. search_listings(description,            │
│                     size, max_price)        │
│       │                                     │
│       ├── results == [] ──────────────────► session["error"] set
│       │                                     RETURN early ◄────────┐
│       │                                                            │
│       └── results != [] ──────────────────► session["selected_item"] = results[0]
│                                             session["search_results"] = results
│                                                    │
│  3. suggest_outfit(selected_item, wardrobe)        │
│       │                                            │
│       │  (wardrobe empty → general advice)         │
│       │  (LLM error → fallback string)             │
│       └──────────────────────────────────► session["outfit_suggestion"]
│                                                    │
│  4. create_fit_card(outfit_suggestion,             │
│                     selected_item)                 │
│       │                                            │
│       │  (empty outfit → error string)             │
│       │  (LLM error → fallback string)             │
│       └──────────────────────────────────► session["fit_card"]
│                                                    │
│  5. return session                                 │
└─────────────────────────────────────────────┘
    │
    ▼
app.py reads session and populates 3 output panels:
  - "Search Result"     ← selected_item title + price + platform + condition
  - "Outfit Suggestion" ← outfit_suggestion
  - "Fit Card"          ← fit_card
  (if error: show error message in Search Result panel, clear others)
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

For `search_listings`: Give Copilot the Tool 1 spec block above (inputs, scoring logic, return value, failure mode) and the `load_listings()` function signature from `utils/data_loader.py`. Ask it to implement the function body inside `tools.py`. Verify: does it filter by both price and size before scoring? Does it return `[]` instead of raising? Test with 3 queries: one that returns results, one that returns nothing, one that checks price filtering.

For `suggest_outfit`: Give Copilot the Tool 2 spec block and the example wardrobe item schema. Ask it to implement using the Groq client already in the file. Verify: does it handle the empty wardrobe case with a different prompt path? Does it wrap the LLM call in try/except? Test with `get_example_wardrobe()` and `get_empty_wardrobe()`.

For `create_fit_card`: Give Copilot the Tool 3 spec block. Ask it to implement with temperature=0.9 and the guard clause for empty outfit. Verify: does the guard run before the LLM call? Does it mention title/price/platform in the prompt? Run 3 times on the same input — outputs must differ.

**Milestone 4 — Planning loop and state management:**

Give Copilot the Architecture diagram above and the Planning Loop section. Ask it to implement `run_agent()` in `agent.py`. Verify before running: does Step 2 branch on `search_results == []`? Does it store `results[0]` in `selected_item` rather than `results`? Does it pass `session["outfit_suggestion"]` (not the raw LLM object) to `create_fit_card`?

For `handle_query()` in `app.py`: Give Copilot the session dict field table and the 3 output panel names from the Gradio layout. Ask it to map session fields to panel strings and handle the error case. Verify: does it check `session["error"]` first?

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:** `run_agent()` initializes the session. The LLM parses the query and returns `{"description": "vintage graphic tee", "size": None, "max_price": 30.0}`. Stored in `session["parsed"]`.

**Step 2:** `search_listings("vintage graphic tee", size=None, max_price=30.0)` is called. It loads all 40 listings, drops anything over $30, then scores the remainder by keyword overlap with "vintage graphic tee". Returns a list sorted by score — top result is something like "Faded Band Tee — $22, Depop, Good condition." Stored in `session["search_results"]`. Since the list is non-empty, `session["selected_item"]` = the top listing dict.

**Step 3:** `suggest_outfit(selected_item, wardrobe)` is called with the full listing dict and the example wardrobe (10 items including baggy jeans, chunky sneakers, black denim jacket). The LLM is prompted with the item details and the wardrobe. Returns: "Pair the faded band tee with your baggy straight-leg jeans and chunky white sneakers for a 90s streetwear look. Layer the vintage black denim jacket on top and tuck the front corner of the tee slightly for shape." Stored in `session["outfit_suggestion"]`.

**Step 4:** `create_fit_card(outfit_suggestion, selected_item)` is called. The LLM receives the outfit string and item details (title, price=$22, platform=depop). Returns: "thrifted this faded band tee off depop for $22 and it was made for my wide-legs 🖤 rolled the sleeves once and tucked the front and suddenly it's an outfit. full look in my stories." Stored in `session["fit_card"]`.

**Final output to user:** Three panels populate in the Gradio UI:
- **Search Result:** "Faded Band Tee — $22 · Depop · Good condition"
- **Outfit Suggestion:** (the outfit string from Step 3)
- **Fit Card:** (the caption from Step 4)

**Error path example:** User queries "designer ballgown size XXS under $5". `search_listings` returns `[]`. `session["error"]` is set to "No listings matched your search. Try a broader description, a different size, or a higher budget." Session returns immediately. `suggest_outfit` and `create_fit_card` are never called. The Search Result panel shows the error message; the other two panels are blank.