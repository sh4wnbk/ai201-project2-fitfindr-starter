import os
import json
import re
from cerebras.cloud.sdk import Cerebras
from tools import search_listings, suggest_outfit, create_fit_card, compare_price

# ──────────────────────────────────────────────
# System / Styling Prompts
# ──────────────────────────────────────────────

PARSER_PROMPT = (
    "You are a data extraction assistant. Parse a thrift shopping query "
    "and extract the item description, clothing size, and maximum price."
)

STYLING_PROMPT = (
    "You are a trendy fashion stylist and personal shopper. "
    "Help users build outfits using thrifted finds and items from their current wardrobe. "
    "Keep your advice practical, stylish, and tailored to the item's vibe."
)

CAPTION_PROMPT = (
    "You are a social media manager creating fashion content. "
    "Generate short, casual, and authentic outfit captions for OOTD posts. "
    "Ensure the caption feels genuine, mentions the item naturally, and matches the vibe."
)

# ── Cerebras Helper for Parsing ───────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """Uses Cerebras llama-3.3-70b to extract search parameters from a query."""
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        return {"description": query, "size": None, "max_price": None}

    client = Cerebras(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model="gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        PARSER_PROMPT
                        + "\n\nRespond with JSON only — no markdown, no explanation. "
                        'Format: {"description": "...", "size": "..." or null, "max_price": number or null}'
                    ),
                },
                {"role": "user", "content": f"Parse this thrift shopping query: {query}"},
            ],
            temperature=0.0,
            max_completion_tokens=600,
        )
        text = response.choices[0].message.content.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        data = json.loads(text)
        return {
            "description": data.get("description", query),
            "size": data.get("size"),
            "max_price": float(data["max_price"]) if data.get("max_price") is not None else None,
        }
    except Exception as e:
        print(f"Error parsing query: {e}")
        return {"description": query, "size": None, "max_price": None}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,              
        "parsed": {},                
        "search_results": [],        
        "selected_item": None,       
        "wardrobe": wardrobe,        
        "adjustments": [],           
        "price_assessment": None,    
        "outfit_suggestion": None,   
        "fit_card": None,            
        "error": None,               
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.
    """
    # Step 1: Initialize the session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the user's query
    session["parsed"] = _parse_query(query)
    
    description = session["parsed"].get("description", query)
    size = session["parsed"].get("size")
    max_price = session["parsed"].get("max_price")

    # Step 3: Call search_listings() with the parsed parameters
    results = search_listings(description, size, max_price)
    session["search_results"] = results
    
    # Step 4: Check if any listings were returned (No-results path guardrail)
    if not results:
        results = search_listings(description, None, max_price)
        session["search_results"] = results
        if results:
            session["adjustments"].append("removed size filter")
        else:
            results = search_listings(description, None, None)
            session["search_results"] = results
            if results:
                session["adjustments"].append("removed price limit")
            else:
                session["error"] = (
                    "No listings matched even after removing the size and price filters. Try a different description."
                )
                return session
        
    # Step 5: Select the top matching item (first item in the sorted results list)
    session["selected_item"] = results[0]

    # Step 6: Compare the selected item's price against category comps
    session["price_assessment"] = compare_price(session["selected_item"])
    
    # Step 7: Generate outfit recommendations using Tool 2
    try:
        session["outfit_suggestion"] = suggest_outfit(session["selected_item"], session["wardrobe"])
    except Exception as e:
        session["error"] = f"Failed to generate outfit suggestion: {e}"
        return session

    # Step 8: Create the social media caption using Tool 3
    try:
        session["fit_card"] = create_fit_card(session["outfit_suggestion"], session["selected_item"])
    except Exception as e:
        session["error"] = f"Failed to create fit card: {e}"
        return session
    
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        title = session["selected_item"].get("title") if session["selected_item"] else "None"
        print(f"Found: {title}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")