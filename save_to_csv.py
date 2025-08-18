from pull_and_collate import create_data_frame
import pandas as pd
import os
from datetime import date

def save_to_csv():
    data = create_data_frame()
    total = data['value'].sum()
    

    filename = 'daily_totals.csv'
    today_str = date.today().isoformat()

    # Prepare the dictionary with 'date', 'total', and fund values
    fund_values = data['value'].to_dict()
    row_dict = {'date': today_str, 'total': total}
    row_dict.update(fund_values)

    if os.path.exists(filename):
        df = pd.read_csv(filename)
        df=df.drop_duplicates()
        # Add any missing fund columns
        for fund in fund_values.keys():
            if fund not in df.columns:
                df[fund] = pd.NA
        if today_str in df['date'].values:
            for key, value in row_dict.items():
                df.loc[df['date'] == today_str, key] = value
        else:
            df = df.append(row_dict, ignore_index=True)
    else:
        df = pd.DataFrame([row_dict])

    df.to_csv(filename, index=False)
