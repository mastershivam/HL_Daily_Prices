
import random,time
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