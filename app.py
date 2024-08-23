import streamlit as st
import pandas as pd

# Merchant ID to Location mapping
merchant_id_mapping = {
    65778282: 'Oslo',
    65796069: 'Oslo',
    65820373: 'Skien',
    65820364: 'Kristiansand',
    65820361: 'Trondheim'
}

def process_files(shopify_df, wordline_df, selected_location):
    try:
        # Ensure all locations are strings and strip "Unaas Cycling" from location names in Shopify data
        shopify_df['Location'] = shopify_df['Location'].astype(str).str.replace('Unaas Cycling ', '', regex=False).str.strip()

        # Map Merchant IDs to Locations in the Wordline data
        wordline_df['Location'] = wordline_df['MERCHANT ID'].map(merchant_id_mapping)
        
        # Filter data based on the selected location
        shopify_df = shopify_df[shopify_df['Location'] == selected_location]
        wordline_df = wordline_df[wordline_df['Location'] == selected_location]

        st.write(f"Filtered Shopify DataFrame shape: {shopify_df.shape}")
        st.write(f"Filtered Wordline DataFrame shape: {wordline_df.shape}")

        # Convert columns to appropriate types
        shopify_df['Total'] = pd.to_numeric(shopify_df['Total'].astype(str).str.replace(',', '').str.replace(' ', ''), errors='coerce')
        wordline_df['SALE AMOUNT'] = pd.to_numeric(wordline_df['SALE AMOUNT'].astype(str).str.replace(',', '').str.replace(' ', ''), errors='coerce')

        # Handle missing values
        shopify_df['Total'].fillna(0, inplace=True)
        wordline_df['SALE AMOUNT'].fillna(0, inplace=True)

        # Adjust for partially paid orders in Shopify
        shopify_df['Paid Amount'] = shopify_df.apply(
            lambda row: row['Total'] - row['Outstanding Balance'] if row['Financial Status'].lower() == 'partially_paid' else row['Total'],
            axis=1
        )

        # Normalize amounts by rounding to 2 decimal places
        shopify_df['Paid Amount'] = shopify_df['Paid Amount'].round(2)
        wordline_df['SALE AMOUNT'] = wordline_df['SALE AMOUNT'].round(2)

        # Convert Wordline date and time columns to datetime
        wordline_df['TRANSACTION_DATETIME'] = pd.to_datetime(
            wordline_df['TRANSACTION DATE'].astype(str) + ' ' + wordline_df['TIME'].astype(str),
            format='%Y-%m-%d %H:%M:%S', errors='coerce'
        )

        # Convert Shopify time column to datetime and remove the timezone info
        shopify_df['Created at'] = pd.to_datetime(shopify_df['Created at'], errors='coerce').dt.tz_localize(None)

        # Ensure Wordline datetime is timezone-naive
        wordline_df['TRANSACTION_DATETIME'] = wordline_df['TRANSACTION_DATETIME'].dt.tz_localize(None)

        # Initialize lists for matched and unmatched records
        matched_records = []
        unmatched_shopify = []
        unmatched_wordline = wordline_df.copy()

        # Matching process with ±5 NOK and ±5 minutes tolerance
        for i, shopify_row in shopify_df.iterrows():
            shopify_amount = shopify_row['Paid Amount']
            shopify_time = shopify_row['Created at']
            match_found = False

            for j, wordline_row in unmatched_wordline.iterrows():
                wordline_amount = wordline_row['SALE AMOUNT']
                wordline_time = wordline_row['TRANSACTION_DATETIME']

                if (abs(shopify_amount - wordline_amount) <= 5 and 
                    abs((shopify_time - wordline_time).total_seconds()) <= 300):  # 5 minutes = 300 seconds
                    matched_records.append({
                        'Shopify Order ID': shopify_row['Id'],  # Assuming 'Id' is unique
                        'Wordline Payment ID': wordline_row['TRANSACTION REF'],  # Adjust as needed
                        'Amount Difference': shopify_amount - wordline_amount,
                        'Time Difference (seconds)': abs((shopify_time - wordline_time).total_seconds()),
                        'Shopify Time': shopify_time,
                        'Wordline Time': wordline_time,
                        'Shopify Amount': shopify_amount,
                        'Wordline Amount': wordline_amount
                    })
                    match_found = True
                    unmatched_wordline = unmatched_wordline.drop(j)  # Remove matched Wordline payment
                    break
            
            if not match_found:
                unmatched_shopify.append(shopify_row)

        # Reorder columns for matched records
        if matched_records:
            matched_df = pd.DataFrame(matched_records)
            st.write("Matched Records:")
            st.dataframe(matched_df)

        # Reorder columns for unmatched Shopify orders
        if unmatched_shopify:
            unmatched_shopify_df = pd.DataFrame(unmatched_shopify)
            unmatched_shopify_df = unmatched_shopify_df[['Name', 'Financial Status', 'Id', 'Created at', 'Paid Amount']]  # Show Name, Financial Status, ID, time, and paid amount
            st.write("Unmatched Shopify Orders:")
            st.dataframe(unmatched_shopify_df)

        # Reorder columns for unmatched Wordline payments
        if not unmatched_wordline.empty:
            unmatched_wordline = unmatched_wordline[['TRANSACTION REF', 'TRANSACTION_DATETIME', 'SALE AMOUNT']]  # Only show ID, time, and amount
            st.write("Unmatched Wordline Payments:")
            st.dataframe(unmatched_wordline)

    except pd.errors.EmptyDataError:
        st.error("The file is empty or could not be read. Please check the file and try again.")
    except pd.errors.ParserError:
        st.error("There was an error parsing the file. Please ensure the file is properly formatted.")
    except Exception as e:
        st.error(f"An unexpected error occurred: {str(e)}")

# Streamlit UI
st.title("Shopify Orders and Wordline Payments Matching")

# Upload files
shopify_file = st.file_uploader("Upload Shopify Orders CSV", type="csv")
wordline_file = st.file_uploader("Upload Wordline Payments Excel", type="xlsx")

if shopify_file and wordline_file:
    try:
        # Read the uploaded files
        shopify_df = pd.read_csv(shopify_file)
        wordline_df = pd.read_excel(wordline_file, sheet_name=1)
        
        # Map Merchant IDs to Locations in the Wordline data
        wordline_df['Location'] = wordline_df['MERCHANT ID'].map(merchant_id_mapping)

        # Get unique locations from both files
        shopify_locations = shopify_df['Location'].dropna().unique().tolist()
        wordline_locations = wordline_df['Location'].dropna().unique().tolist()

        # Combine and sort locations, ensuring no NaNs
        all_locations = sorted(list(set(shopify_locations + wordline_locations)), key=str)

        # Remove any potential 'nan' entries from the list
        all_locations = [loc for loc in all_locations if loc.lower() != 'nan']

        # Let the user select the location
        selected_location = st.selectbox("Select the Location to Match", all_locations)

        # Process files with selected location
        process_files(shopify_df, wordline_df, selected_location)

    except pd.errors.EmptyDataError:
        st.error("One or both files are empty. Please upload valid files.")
    except pd.errors.ParserError:
        st.error("There was an error parsing the file. Please ensure the file is properly formatted.")
    except Exception as e:
        st.error(f"An unexpected error occurred: {str(e)}")
