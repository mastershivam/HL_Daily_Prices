import requests
from price_scraper import price_scraper_fund
import pandas as pd
import locale, random,time
from forex_python.converter import CurrencyRates, RatesNotAvailableError

for loc in ('en_GB.UTF-8', 'en_US.UTF-8', 'C.UTF-8'):
    try:
        locale.setlocale(locale.LC_ALL, loc)
        break
    except locale.Error:
        continue


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


def get_usd_gbp_rate(retries=3, base_delay=1.0, max_delay=20.0):
    c = CurrencyRates()
    attempt = 0
    while True:
        try:
            return c.get_rate('USD', 'GBP')
        except RatesNotAvailableError as e:
            
            
            delay = min(base_delay * (2 ** (attempt)), max_delay)
            jitter = random.uniform(0.9, 1.1)
            delay *= jitter
            print(f"[Retry {attempt}/{retries}] Rates not ready (likely upstream delay). Retrying in {delay:.1f} s…")
            time.sleep(delay)
            if attempt >= retries:
                print(f"[Error] Still failing after {retries} retries. Using Frankfurters")

                data=(requests.get('https://api.frankfurter.dev/v1/latest?base=USD&symbols=GBP')).json()
                return data["rates"]["GBP"] 
            attempt += 1


def create_data_frame():
    
    with open("urls.txt", "r") as f:
        urls = []
        for line in f:
            if line.strip():  # skip blank lines
                urls.append(line.strip())  # add trimmed line to the list

    # Load units CSV and set index to normalised key of the fund name
    # Expected columns in units.csv: fund, units (and any others you need)
    units_df = pd.read_csv("units.csv")
    if "fund" not in units_df.columns:
        raise ValueError("units.csv must contain a 'fund' column for matching.")
    units_df["key"] = units_df["fund"].apply(normalise_key)
    units_df = units_df.set_index("key")

    # Pull scraped data and build a DataFrame indexed by the same normalized key
    temp_data = []
    for url in urls:
        
        data = price_scraper_fund(url)  # should return dict with at least 'title'
        if not isinstance(data, dict) or "title" not in data:
            raise ValueError("price_scraper_func(url) must return a dict including 'title'")
        data["key"] = normalise_key(data["title"])
        data["url"] = url
        temp_data.append(data)

    fund_data_df = pd.DataFrame(temp_data).set_index("key")

    merged_data_df = units_df.join(fund_data_df, how="inner", rsuffix="_src")

    if "fund" in merged_data_df.columns:
        merged_data_df = merged_data_df.set_index("fund")

        
    merged_data_df['currency'] = merged_data_df['sell'].str.contains('$', regex=False).map(lambda has_dollar: 'USD' if has_dollar else 'GBP')
    merged_data_df['sell'] = merged_data_df['sell'].str.replace('$', '', regex=False)
    merged_data_df['sell']=(merged_data_df['sell'].map(lambda value: locale.atof(value[:-1])))
    merged_data_df.astype({'sell': 'complex128'}).dtypes
    
    merged_data_df['value']=(merged_data_df['units']*merged_data_df['sell'])

    cols_to_divide = ["sell", "value"]
    mask = ~merged_data_df.index.str.contains("share", case=False)
    merged_data_df.loc[mask, cols_to_divide] = merged_data_df.loc[mask, cols_to_divide] / 100   

    
    USD_GBP_Rate=get_usd_gbp_rate(retries=1,base_delay=2.0,max_delay=20.0)
    usd_mask = merged_data_df['currency'] == 'USD'
    merged_data_df.loc[usd_mask, 'value'] *= USD_GBP_Rate
    merged_data_df.loc[usd_mask, 'currency'] = 'GBP'
    
    merged_data_df=merged_data_df.drop('title',axis=1)
    rename_dict={'fund':'Fund','units':'Units','sell':'Sell Price','buy':'Buy Price','change_value':'Change Value','change_pct':'Percentage Change','url':'URL','currency':'Currency','value':'Total Holding Value'}
    merged_data_df=merged_data_df.rename(rename_dict,axis=1)
    
    return merged_data_df

