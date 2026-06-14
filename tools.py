"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

from utils.data_loader import load_listings

load_dotenv()


# ── Gemini client ─────────────────────────────────────────────────────────────

def _get_gemini_client():
    """Initialize and return a Gemini client using GEMINI_API_KEY from .env."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not set. Add it to a .env file in the project root."
        )
    return genai.Client(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    try:
        listings = load_listings()
        search_words = description.lower().split()
        scored_listings = []

        for listing in listings:
            try:
                price = listing.get("price")
                if max_price is not None and price is not None and price > max_price:
                    continue

                if size is not None:
                    listing_size = str(listing.get("size", "")).lower()
                    if size.lower() not in listing_size:
                        continue

                combined_text = (
                    f"{listing.get('title', '')} {listing.get('description', '')} "
                    f"{' '.join(listing.get('style_tags', []))} "
                    f"{' '.join(listing.get('colors', []))} "
                    f"{listing.get('brand') or ''}"
                ).lower()

                score = sum(1 for word in search_words if word in combined_text)
                if score > 0:
                    scored_listings.append((score, listing))
            except Exception:
                continue

        scored_listings.sort(key=lambda item: item[0], reverse=True)
        return [listing for _, listing in scored_listings]
    except Exception:
        return []


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    try:
        client = _get_gemini_client()
        items = wardrobe.get("items") or []

        item_title = new_item.get("title", "this item")
        item_description = new_item.get("description", "")
        item_style_tags = ", ".join(new_item.get("style_tags", []))
        item_colors = ", ".join(new_item.get("colors", []))

        system_instruction = (
            "You are a practical, fashion-savvy stylist. Give clear, specific, "
            "and helpful outfit advice. Keep suggestions concise, grounded, and easy to wear."
        )

        if not items:
            prompt = (
                f"Suggest general styling advice for this thrifted item:\n"
                f"Title: {item_title}\n"
                f"Description: {item_description}\n"
                f"Style tags: {item_style_tags}\n"
                f"Colors: {item_colors}\n\n"
                "Explain what kinds of pieces pair well with it, what vibe it suits, "
                "and any simple outfit formulas that would work."
            )
        else:
            wardrobe_lines = []
            for wardrobe_item in items:
                name = wardrobe_item.get("name", "Unnamed item")
                category = wardrobe_item.get("category", "unknown category")
                colors = ", ".join(wardrobe_item.get("colors", []))
                notes = wardrobe_item.get("notes", "")
                wardrobe_lines.append(f"- {name} ({category}, {colors}, {notes})")

            prompt = (
                f"Suggest 1-2 outfit combinations using this thrifted item:\n"
                f"Title: {item_title}\n"
                f"Description: {item_description}\n"
                f"Style tags: {item_style_tags}\n"
                f"Colors: {item_colors}\n\n"
                "Wardrobe items:\n"
                + "\n".join(wardrobe_lines)
                + "\n\nUse the new item and name specific wardrobe pieces in each outfit."
            )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                max_output_tokens=400,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return response.text
    except Exception:
        return "Couldn't generate outfit suggestions right now. Try describing your wardrobe and I can help manually."


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not outfit or not outfit.strip():
        return "Unable to generate a fit card — outfit description was missing."

    try:
        client = _get_gemini_client()

        item_title = new_item.get("title", "this item")
        item_price = new_item.get("price", "unknown price")
        item_platform = new_item.get("platform", "unknown platform")
        item_condition = new_item.get("condition", "unknown condition")

        system_instruction = (
            "You write casual, lowercase ootd captions with a specific, natural voice. "
            "Keep the caption 2-4 sentences, avoid generic phrasing, and make it sound like a real post."
        )

        prompt = (
            f"Write a 2-4 sentence lowercase casual ootd caption for this thrift find.\n"
            f"Item name: {item_title}\n"
            f"Price: {item_price}\n"
            f"Platform: {item_platform}\n"
            f"Condition: {item_condition}\n"
            f"Outfit: {outfit}\n\n"
            "Requirements: mention the item name, price, and platform once each; capture the vibe in specific terms; "
            "do not use generic phrases like 'love this look'."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.9,
                max_output_tokens=200,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return response.text
    except Exception:
        return "Fit card generation failed. Here's the outfit suggestion instead: " + outfit
