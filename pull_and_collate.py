from utilities import get_usd_gbp_rate, improved_normalise_key
from price_scraper import price_scraper_fund
import pandas as pd
import locale
import os

def create_data_frame(debug=False):
    
    # Load units CSV and set index to normalised key of the fund name
    # Expected columns in units.csv: fund, units (and any others you need)

    units_path = os.path.join('HL_Daily_Prices_Data', 'units.csv')
    units_df = pd.read_csv(units_path)
    
    # Remove empty rows (where all values are NaN)
    units_df = units_df.dropna(how='all')
    
    if "fund" not in units_df.columns:
        raise ValueError("units.csv must contain a 'fund' column for matching.")
    
    # Remove rows where fund name is missing
    units_df = units_df.dropna(subset=['fund'])
    
    # Check for missing required columns
    missing_columns = []
    if 'units' not in units_df.columns:
        missing_columns.append('units')
    if 'url' not in units_df.columns:
        missing_columns.append('url')
    
    if missing_columns:
        raise ValueError(f"units.csv is missing required columns: {', '.join(missing_columns)}")
    
    # Remove rows where required data is missing
    units_df = units_df.dropna(subset=['units', 'url'])
    
    if debug:
        print(f"Processing {len(units_df)} funds from units.csv")
        print("Funds:", units_df['fund'].tolist())
    
    units_df["key"] = units_df["fund"].apply(improved_normalise_key)
    units_df = units_df.set_index("key")

    # Pull scraped data and build a DataFrame indexed by the same normalised key
    temp_data = []
    urls = units_df['url'].to_list()
    fund_names = units_df['fund'].to_list()
    
    for i, (url, fund_name) in enumerate(zip(urls, fund_names)):
        try:
            if debug:
                print(f"Scraping {i+1}/{len(urls)}: {fund_name}")
            data = price_scraper_fund(url)  # should return dict with at least 'title'
            if debug:
                print(data)
            if not isinstance(data, dict) or "title" not in data:
                print(f"Warning: Failed to scrape {fund_name} - no title found")
                continue
            data["key"] = improved_normalise_key(data["title"])
            data["url"] = url
            data["fund_name"] = fund_name  # Keep original fund name for reference
            temp_data.append(data)
            if debug:
                print(f"Successfully scraped: {data['title']}")
        except Exception as e:
            print(f"Error scraping {fund_name} ({url}): {str(e)}")
            continue

    if not temp_data:
        raise ValueError("No funds were successfully scraped. Check your URLs and network connection.")

    fund_data_df = pd.DataFrame(temp_data).set_index("key")
    if debug:
        print(f"Successfully scraped {len(fund_data_df)} out of {len(units_df)} funds")

    # Use left join to include all funds from units.csv, even if scraping failed
    merged_data_df = units_df.join(fund_data_df, how="left", rsuffix="_src")

    if "fund" in merged_data_df.columns:
        merged_data_df = merged_data_df.set_index("fund")

    # Check for funds that failed to scrape
    failed_funds = merged_data_df[merged_data_df['title'].isna()]
    if not failed_funds.empty:
        print(f"Warning: {len(failed_funds)} funds failed to scrape and will be excluded:")
        for fund in failed_funds.index:
            print(f"  - {fund}")
    
    # Remove funds that failed to scrape (have NaN values for required fields)
    merged_data_df = merged_data_df.dropna(subset=['title', 'sell'])
    
    if merged_data_df.empty:
        raise ValueError("No funds have valid scraped data. All scraping attempts failed.")
    
    if debug:
        print(f"Processing {len(merged_data_df)} funds with valid data")
        
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
    'units':'Units',
    'sell':'Sell Price',
    'buy':'Buy Price',
    'change_value':'Change Value',
    'change_pct':'Percentage Change',
    'url':'URL','currency':'Currency',
    'value':'Total Holding Value'
    }
    merged_data_df=merged_data_df.rename(rename_dict,axis=1)
    merged_data_df.index.name='Fund/Share'

    
    return merged_data_df

