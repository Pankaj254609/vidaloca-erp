import streamlit as st
import pandas as pd
import os
from datetime import datetime

st.set_page_config(page_title="Vida Loca Advanced ERP", layout="wide")

# Database Files mapped precisely to your sheets
PROD_FILE = "master_sku.csv"
MAP_FILE = "channel_sku_map.csv"
SALES_FILE = "sale_data.csv"
STOCK_FILE = "add_inventory.csv"

def load_data():
    if not os.path.exists(PROD_FILE):
        pd.DataFrame(columns=["Category Code", "Product Code", "Name", "Scan Identifier", "Color", "Size", "Brand", "Type", "Component Product Code", "QTY", "Image URL"]).to_csv(PROD_FILE, index=False)
    if not os.path.exists(MAP_FILE):
        pd.DataFrame(columns=["Seller SKU on Channel", "SKU Code", "channelName", "PACK OF", "BRAND"]).to_csv(MAP_FILE, index=False)
    if not os.path.exists(SALES_FILE):
        pd.DataFrame(columns=["Date", "Channel SKU", "BRAND", "QTY"]).to_csv(SALES_FILE, index=False)
    if not os.path.exists(STOCK_FILE):
        pd.DataFrame(columns=["Date & Time", "Product Code", "Added QTY"]).to_csv(STOCK_FILE, index=False)

    df_p = pd.read_csv(PROD_FILE)
    # Safe column migration check (fixes prior bug cleanly)
    if "Image URL" not in df_p.columns:
        df_p["Image URL"] = ""
        df_p.to_csv(PROD_FILE, index=False)

    return pd.read_csv(PROD_FILE), pd.read_csv(MAP_FILE), pd.read_csv(SALES_FILE), pd.read_csv(STOCK_FILE)

df_prod, df_map, df_sales, df_stock = load_data()

# 🧠 E-commerce Bundle & Single SKU Inventory Processing Engine
def get_actual_inventory():
    df_p, df_m, df_sa, df_st = load_data()
    
    # 1. Calculate Inward stock (Opening QTY + Warehouse Additions)
    inward_stock = df_p.set_index('Product Code')['QTY'].to_dict()
    for _, row in df_st.iterrows():
        p_code = row['Product Code']
        if p_code in inward_stock:
            inward_stock[p_code] += row['Added QTY']
            
    # 2. Process Order Sales Deductions based on mapped items
    sold_stock = {p_code: 0 for p_code in df_p['Product Code'].values}
    
    for _, sale in df_sa.iterrows():
        c_sku = sale['Channel SKU']
        s_qty = int(sale['QTY']) if pd.notna(sale['QTY']) else 0
        
        mapping = df_m[df_m['Seller SKU on Channel'] == c_sku]
        if not mapping.empty:
            for _, map_row in mapping.iterrows():
                linked_sku = map_row['SKU Code']
                
                # Check if linked SKU maps down into components inside MASTER SKU sheet
                master_components = df_p[df_p['Product Code'] == linked_sku]
                if not master_components.empty:
                    for _, comp_row in master_components.iterrows():
                        comp_sku = comp_row['Component Product Code']
                        if comp_sku in sold_stock:
                            sold_stock[comp_sku] += s_qty
                else:
                    if linked_sku in sold_stock:
                        sold_stock[linked_sku] += s_qty
        else:
            # Direct deduction if channel match equals Master SKU directly
            if c_sku in sold_stock:
                sold_stock[c_sku] += s_qty

    # 3. Compile closing balanced data
    balance_list = []
    total_sold_list = []
    for _, row in df_p.iterrows():
        p_code = row['Product Code']
        total_in = inward_stock.get(p_code, 0)
        total_sold = sold_stock.get(p_code, 0)
        balance_list.append(total_in - total_sold)
        total_sold_list.append(total_sold)
        
    df_p['Total Sold QTY'] = total_sold_list
    df_p['Actual Balance Stock'] = balance_list
    return df_p

# ---- Sidebar Configuration Navigation Panel ----
st.sidebar.title("👑 Vida Loca ERP System")
menu = st.sidebar.radio("Navigation Control Panel:", [
    "📊 Live Dashboard", 
    "📦 1. MASTER SKU Sheet", 
    "🔗 2. CHANEL SKU MAP Sheet",
    "📥 3. ADD INVENTORY Sheet", 
    "📤 4. SALE DATA Sheet"
])

# ==================== LIVE DASHBOARD ====================
if menu == "📊 Live Dashboard":
    st.title("📊 Live Stock & Inventory Dashboard")
    df_actual = get_actual_inventory()
    
    st.sidebar.write("### 🎛️ Quick Filters")
    brands = ["All"] + list(df_actual['Brand'].dropna().unique())
    selected_brand = st.sidebar.selectbox("Filter by Brand Name", brands)
    
    types = ["All"] + list(df_actual['Type'].dropna().unique())
    selected_type = st.sidebar.selectbox("Filter by Stock Type (SIMPLE/BUNDLE)", types)
    
    if selected_brand != "All": df_actual = df_actual[df_actual['Brand'] == selected_brand]
    if selected_type != "All": df_actual = df_actual[df_actual['Type'] == selected_type]
        
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Unique Master SKUs", len(df_actual))
    col2.metric("Total Ordered/Sold QTY", int(df_actual['Total Sold QTY'].sum()))
    col3.metric("Live Available Warehouse Stock", int(df_actual['Actual Balance Stock'].sum()))
    
    st.write("---")
    st.subheader("📋 Product closing summary report")
    
    st.dataframe(
        df_actual[["Image URL", "Product Code", "Name", "Color", "Size", "Brand", "Type", "QTY", "Total Sold QTY", "Actual Balance Stock"]], 
        column_config={"Image URL": st.column_config.ImageColumn("Product Preview Link")},
        use_container_width=True
    )

# ==================== 1. MASTER SKU SHEET ====================
elif menu == "📦 1. MASTER SKU Sheet":
    st.title("📦 Master SKU Inventory Dataset Management")
    tab1, tab2 = st.tabs(["📁 Bulk File Upload (Excel/CSV)", "✍️ Single Manual Entry"])
    
    with tab1:
        st.subheader("Bulk Sync your 'MASTER SKU' Template Sheet")
        st.info("Columns order needed in file: `Category Code`, `Product Code`, `Name`, `Scan Identifier`, `Color`, `Size`, `Brand`, `Type`, `Component Product Code`, `QTY`, `Image URL`")
        uploaded_file = st.file_uploader("Upload Excel / CSV Sheet directly", type=["xlsx", "csv"], key="master_upload")
        if uploaded_file is not None:
            bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            st.dataframe(bulk_df.head())
            if st.button("🚀 Process & Sync Master Data"):
                bulk_df.to_csv(PROD_FILE, index=False)
                st.success("Master dataset processed successfully!")
                st.rerun()
    with tab2:
        with st.form("master_form", clear_on_submit=True):
            cat = st.text_input("Category Code", "KURTA")
            p_code = st.text_input("Product Code (Unique Master SKU ID)").upper().strip()
            name = st.text_input("Product Display Description")
            color = st.text_input("Color variant")
            size = st.text_input("Size tag")
            brand = st.text_input("Brand Identifier", "Vida Loca")
            p_type = st.selectbox("Stock Strategy Classification Type", ["SIMPLE", "BUNDLE"])
            comp_code = st.text_input("Component Breakdown Mapping Product Code")
            qty = st.number_input("Warehouse Opening Quantity", min_value=0, value=0)
            img_url = st.text_input("Product Image direct URL path link")
            
            if st.form_submit_button("Append Single Item Record") and p_code:
                pd.DataFrame([[cat, p_code, name, p_code, color, size, brand, p_type, comp_code, qty, img_url]], columns=df_prod.columns).to_csv(PROD_FILE, mode='a', header=False, index=False)
                st.success("New SKU configuration committed successfully!")
                st.rerun()
    st.dataframe(df_prod, use_container_width=True)

# ==================== 2. CHANEL SKU MAP SHEET ====================
elif menu == "🔗 2. CHANEL SKU MAP Sheet":
    st.title("🔗 Channel Marketplace SKU Mapping Table")
    tab1, tab2 = st.tabs(["📁 Bulk Mapping File Upload", "✍️ Add Individual Mapping Code"])
    
    with tab1:
        st.subheader("Upload marketplace 'CHANEL SKU' file connection template")
        st.info("Headers alignment must match: `Seller SKU on Channel`, `SKU Code`, `channelName`, `PACK OF`, `BRAND`")
        uploaded_file = st.file_uploader("Upload Connection Mapping file", type=["xlsx", "csv"], key="map_upload")
        if uploaded_file is not None:
            bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            st.dataframe(bulk_df.head())
            if st.button("🚀 Process & Sync Link Map Table"):
                bulk_df.to_csv(MAP_FILE, index=False)
                st.success("Mapping configuration tables linked successfully!")
                st.rerun()
    with tab2:
        with st.form("map_form", clear_on_submit=True):
            c_sku = st.text_input("Seller SKU listed on Channels").strip()
            m_sku = st.text_input("Target SKU Code to bind against").strip()
            ch_name = st.text_input("Channel/Portal Identifier Name (e.g. FLIPKART, MEESHO)")
            pack_of = st.selectbox("Pack Classification Config", ["SINGLE", "BUNDLE"])
            brand = st.text_input("BRAND Name Reference", "VIDA LOCA")
            if st.form_submit_button("Commit Mapping Connection Record") and c_sku:
                pd.DataFrame([[c_sku, m_sku, ch_name, pack_of, brand]], columns=df_map.columns).to_csv(MAP_FILE, mode='a', header=False, index=False)
                st.success("Mapping connected successfully!")
                st.rerun()
    st.dataframe(df_map, use_container_width=True)

# ==================== 3. ADD INVENTORY SHEET ====================
elif menu == "📥 3. ADD INVENTORY Sheet":
    st.title("📥 Fresh Warehouse Stock Inward Load")
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with st.form("stock_form", clear_on_submit=True):
        p_code = st.selectbox("Choose Targeted Active Product Code", df_prod['Product Code'].values if not df_prod.empty else [])
        add_qty = st.number_input("Inward Batch Load QTY to append", min_value=1, value=1)
        if st.form_submit_button("Commit Fresh Batch Inventory QTY") and p_code:
            pd.DataFrame([[current_time, p_code, add_qty]], columns=df_stock.columns).to_csv(STOCK_FILE, mode='a', header=False, index=False)
            st.success("Physical stock ledger incremented successfully!")
            st.rerun()
    st.dataframe(df_stock, use_container_width=True)

# ==================== 4. SALE DATA SHEET ====================
elif menu == "📤 4. SALE DATA Sheet":
    st.title("📤 Sales Manifest Processing Data Sheet")
    tab1, tab2 = st.tabs(["📁 Import Bulk Marketplace Dispatched Sheets", "✍️ Manual Individual Sale Item Log"])
    
    with tab1:
        st.subheader("Upload downloaded daily orders manifest spreadsheet")
        st.info("Columns validation required: `Date`, `Channel SKU`, `BRAND`, `QTY`")
        uploaded_file = st.file_uploader("Upload manifest logs file", type=["xlsx", "csv"], key="sale_upload")
        if uploaded_file is not None:
            bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            st.dataframe(bulk_df.head())
            if st.button("🚀 Process Daily Invoices & Deplete Live Inventory"):
                bulk_df.to_csv(SALES_FILE, index=False)
                st.success("Order metrics evaluated. All mapped inventory levels depleted cleanly!")
                st.rerun()
    with tab2:
        with st.form("sale_form", clear_on_submit=True):
            s_date = st.date_input("Invoice Transaction Date").strftime("%Y-%m-%d")
            c_sku = st.text_input("Channel SKU transactional key lookup code")
            brand = st.text_input("BRAND Name Reference Label", "VIDA LOCA")
            qty = st.number_input("Sales Outward Volume Units QTY count", min_value=1, value=1)
            if st.form_submit_button("Commit Manual Sales Log Entry") and c_sku:
                pd.DataFrame([[s_date, c_sku, brand, qty]], columns=df_sales.columns).to_csv(SALES_FILE, mode='a', header=False, index=False)
                st.success("Sales entry successfully populated into databases!")
                st.rerun()
    st.dataframe(df_sales, use_container_width=True)