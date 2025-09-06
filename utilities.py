
import requests

def get_usd_gbp_rate():
    data=(requests.get('https://api.frankfurter.dev/v1/latest?base=USD&symbols=GBP')).json()
    return data["rates"]["GBP"] 
            

def normalise_key(s: str) -> str:
    """Normalise a fund/title string for reliable matching."""
    if s is None:
        return ""
    return (
        str(s)
        .strip()
        .casefold()
        .replace(" & ", " and ")
        .replace("&", " and ")
        .replace("  ", " ")
    )

    # Improved normalization to handle common fund name variations
def improved_normalise_key(s: str) -> str:
    """Enhanced normalization for fund names to handle common variations."""
    if s is None:
        return ""
    normalized = (
        str(s)
        .strip()
        .casefold()
        .replace(" & ", " and ")
        .replace("&", " and ")
        .replace("  ", " ")
        .replace("indexaccumulation", "index accumulation")  # Fix the specific issue
        .replace("indexdistribution", "index distribution")  # Handle similar cases
        .replace("class a", "class a")
        .replace("class b", "class b")
        .replace("class c", "class c")
    )
    return normalized
