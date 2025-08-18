from utilities import get_usd_gbp_rate, normalise_key
from price_scraper import price_scraper_fund
import pandas as pd
import locale


def create_data_frame():
    
    # Load units CSV and set index to normalised key of the fund name
    # Expected columns in units.csv: fund, units (and any others you need)
    units_df = pd.read_csv("units.csv")
    if "fund" not in units_df.columns:
        raise ValueError("units.csv must contain a 'fund' column for matching.")
    units_df["key"] = units_df["fund"].apply(normalise_key)
    units_df = units_df.set_index("key")

    # Pull scraped data and build a DataFrame indexed by the same normalized key
    temp_data = []
    urls=units_df['url'].to_list()
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

    
    USD_GBP_Rate=get_usd_gbp_rate()
    usd_mask = merged_data_df['currency'] == 'USD'
    merged_data_df.loc[usd_mask, 'value'] *= USD_GBP_Rate
    merged_data_df.loc[usd_mask, 'currency'] = 'GBP'
    
    merged_data_df=merged_data_df.drop(['title','url_src'],axis=1)
    
    rename_dict={
    'fund':'Fund',
    'units':'Units',
    'sell':'Sell Price',
    'buy':'Buy Price',
    'change_value':'Change Value',
    'change_pct':'Percentage Change',
    'url':'URL','currency':'Currency',
    'value':'Total Holding Value'
    }
    merged_data_df=merged_data_df.rename(rename_dict,axis=1)
    
    return merged_data_df

