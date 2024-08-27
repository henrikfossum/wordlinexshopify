import streamlit as st
import pandas as pd

# Custom CSS for reducing padding
st.markdown("""
    <style>
    .stFileUploader label, .stSelectbox label {
        font-size: 16px;
        margin-bottom: 0px;
        padding-bottom: 0px;
    }
    .stFileUploader .uploadLabel, .stSelectbox .uploadLabel {
        margin-top: 0px;
        padding-top: 0px;
    }
    </style>
""", unsafe_allow_html=True)

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
        # Filter out transactions with "Svea Checkout" in Shopify data
        shopify_df = shopify_df[shopify_df['Payment Method'] != 'Svea Checkout']

        # Ensure all locations are strings and strip "Unaas Cycling" from location names in Shopify data
        shopify_df['Location'] = shopify_df['Location'].astype(str).str.replace('Unaas Cycling ', '', regex=False).str.strip()

        # Map Merchant IDs to Locations in the Wordline data
        wordline_df['Location'] = wordline_df['MERCHANT ID'].map(merchant_id_mapping)
        
        # Filter data based on the selected location
        shopify_df = shopify_df[shopify_df['Location'] == selected_location]
        wordline_df = wordline_df[wordline_df['Location'] == selected_location]

        st.write(f"Filtrert Shopify DataFrame form: {shopify_df.shape}")
        st.write(f"Filtrert Wordline DataFrame form: {wordline_df.shape}")

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
                    abs((shopify_time - wordline_time).total_seconds()) <= 300):  # 5 minutter = 300 sekunder
                    matched_records.append({
                        'Shopify Name': shopify_row['Name'],  # Inkluder Shopify Name
                        'Shopify Order ID': shopify_row['Id'],  # Antatt unik 'Id'
                        'Shopify Amount': shopify_amount,
                        'Wordline Amount': wordline_amount,
                        'Amount Difference': shopify_amount - wordline_amount,
                        'Shopify Time': shopify_time,
                        'Wordline Time': wordline_time,
                        'Time Difference (seconds)': abs((shopify_time - wordline_time).total_seconds()),
                        'Wordline Payment ID': wordline_row['TRANSACTION REF']  # Juster ved behov
                    })
                    match_found = True
                    unmatched_wordline = unmatched_wordline.drop(j)  # Fjern matchet Wordline betaling
                    break
            
            if not match_found:
                unmatched_shopify.append(shopify_row)

        # Reorder columns for matched records
        if matched_records:
            matched_df = pd.DataFrame(matched_records)
            matched_df = matched_df[
                ['Shopify Name', 'Shopify Order ID', 'Shopify Amount', 'Wordline Amount', 'Amount Difference', 'Shopify Time', 'Wordline Time', 'Time Difference (seconds)', 'Wordline Payment ID']
            ]
            st.markdown('<h2 style="text-align:center;">Matchende ordre:</h2>', unsafe_allow_html=True)
            st.dataframe(matched_df)

        # Side-by-Side Display for Unmatched Records
        st.markdown('<h2 style="text-align:center;">Sammenligning av ordre og betalinger uten match</h2>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)

        with col1:
            st.write("Umatchede Shopify Ordre:")
            unmatched_shopify_df = pd.DataFrame(unmatched_shopify)
            if not unmatched_shopify_df.empty:
                unmatched_shopify_df = unmatched_shopify_df[['Name', 'Paid Amount', 'Created at', 'Id']]  # Vis relevante kolonner
                st.dataframe(unmatched_shopify_df)
            else:
                st.write("Ingen umatchede Shopify ordre.")

        with col2:
            st.write("Umatchede Wordline Betalinger:")
            if not unmatched_wordline.empty:
                unmatched_wordline_df = unmatched_wordline[['SALE AMOUNT', 'TRANSACTION_DATETIME', 'TRANSACTION REF']]  # Vis relevante kolonner
                st.dataframe(unmatched_wordline_df)
            else:
                st.write("Ingen umatchede Wordline betalinger.")

    except pd.errors.EmptyDataError:
        st.error("En eller begge filene er tomme. Vennligst last opp gyldige filer.")
    except pd.errors.ParserError:
        st.error("Det oppsto en feil ved parsing av filen. Vennligst sørg for at filen er riktig formatert.")
    except Exception as e:
        st.error(f"En uventet feil oppsto: {str(e)}")

# Streamlit UI
st.title("Shopify Ordre og Wordline Betalinger Matching")

# Upload files
st.markdown('<div style="margin-bottom: -15px;"><label style="font-size:18px;">Last opp Shopify Ordre CSV</label></div>', unsafe_allow_html=True)
shopify_file = st.file_uploader("", type="csv")
st.markdown('<div style="margin-bottom: -15px;"><label style="font-size:18px;">Last opp Wordline Betalinger Excel</label></div>', unsafe_allow_html=True)
wordline_file = st.file_uploader("", type="xlsx")

if shopify_file and wordline_file:
    try:
        # Les de opplastede filene
        shopify_df = pd.read_csv(shopify_file)
        wordline_df = pd.read_excel(wordline_file, sheet_name=1)
        
        # Map Merchant IDs til Lokasjoner i Wordline data
        wordline_df['Location'] = wordline_df['MERCHANT ID'].map(merchant_id_mapping)

        # Hent unike lokasjoner fra begge filer
        shopify_locations = shopify_df['Location'].dropna().unique().tolist()
        wordline_locations = wordline_df['Location'].dropna().unique().tolist()

        # Kombiner og sorter lokasjoner, og sørg for at ingen NaNs
        all_locations = sorted(list(set(shopify_locations + wordline_locations)), key=str)

        # Fjern eventuelle 'nan' oppføringer fra listen
        all_locations = [loc for loc in all_locations if loc.lower() != 'nan']

        # La brukeren velge lokasjon
        st.markdown('<div style="margin-bottom: -15px;"><label style="font-size:18px;">Velg Lokasjon å Matche</label></div>', unsafe_allow_html=True)
        selected_location = st.selectbox("", all_locations)

        # Behandle filer med valgt lokasjon
        process_files(shopify_df, wordline_df, selected_location)

    except pd.errors.EmptyDataError:
        st.error("En eller begge filene er tomme. Vennligst last opp gyldige filer.")
    except pd.errors.ParserError:
        st.error("Det oppsto en feil ved parsing av filen. Vennligst sørg for at filen er riktig formatert.")
    except Exception as e:
        st.error(f"En uventet feil oppsto: {str(e)}")
