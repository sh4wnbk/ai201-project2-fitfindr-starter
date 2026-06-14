import os
import json
from typing import Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
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

# ── Gemini Structured Output Schema ───────────────────────────────────────────

class QueryTemplate(BaseModel):
    description: str = Field(description="Keywords describing the clothing item (e.g., 'vintage graphic tee').")
    size: Optional[str] = Field(None, description="The requested clothing size (e.g., 'M', 'S', 'L', 'XXS'). If not mentioned, return null.")
    max_price: Optional[float] = Field(None, description="The numerical maximum price constraint (e.g., 30.0). Do not include dollar signs. If not mentioned, return null.")

# ── Gemini Helper for Parsing ──────────────────────────────────────────────────

def _parse_query_with_gemini(query: str) -> dict:
    """Uses gemini-2.5-flash native structured output to extract search parameters safely."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"description": query, "size": None, "max_price": None}
        
    client = genai.Client(api_key=api_key)
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=f"Parse this thrift shopping query: {query}",
            config=types.GenerateContentConfig(
                system_instruction=PARSER_PROMPT,
                response_mime_type="application/json",
                response_schema=QueryTemplate,
            )
        )
        data: QueryTemplate = response.parsed
        return {
            "description": data.description,
            "size": data.size,
            "max_price": data.max_price
        }
    except Exception as e:
        print(f"Error parsing query with Gemini: {e}")
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

    # Step 2: Parse the user's query using our Gemini helper
    session["parsed"] = _parse_query_with_gemini(query)
    
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