import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, time

# --- Theme Configuration ---
st.set_page_config(page_title="Vida Loca Advanced ERP", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    h1, h2, h3 { color: #1e293b; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-weight: 700; }
    [data-testid="stSidebar"] { background-color: #0f172a !important; color: #ffffff !important; }
    [data-testid="stSidebar"] *.stText, [data-testid="stSidebar"] label, [data-testid="stSidebar"] h1 { color: #ffffff !important; }
    .metric-container {
        background-color: #ffffff; border-radius: 12px; padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border-left: 6px solid #3b82f6; margin-bottom: 15px;
    }
    .metric-title { font-size: 14px; color: #64748b; font-weight: 600; text-transform: uppercase; }
    .metric-value { font-size: 28px; color: #1e293b; font-weight: 700; margin-top: 5px; }
    .card-blue { border-left-color: #3b82f6; }
    .card-orange { border-left-color: #f97316; }
    .card-green { border-left-color: #10b981; }
    .stButton>button {
        background-color: #3b82f6 !important; color: white !important;
        border-radius: 8px !important; padding: 8px 24px !important; font-weight: 600 !important; border: none !important;
    }
    .stButton>button:hover { background-color: #2563eb !important; }
    </style>
""", unsafe_allow_html=True)

# Database Files
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
    if "Image URL" not in df_p.columns:
        df_p["Image URL"] = ""
        df_p.to_csv(PROD_FILE, index=False)

    # ⏰ 12:00 PM AUTOMATIC DAILY RESET LOGIC
    # Checks if the last reset milestone has passed today
    df_st = pd.read_csv(STOCK_FILE)
    if not df_st.empty:
        try:
            now = datetime.now()
            # If current time is past 12:00 PM
            if now.time() >= time(12, 0):
                # Parse last entry timestamp
                last_entry_time = pd.to_datetime(df_st['Date & Time'].iloc[-1])
                # If last entry was before 12:00 PM today, clear old stock data
                if last_entry_time.date() < now.date() or (last_entry_time.date() == now.date() and last_entry_time.time() < time(12, 0)):
                    pd.DataFrame(columns=["Date & Time", "Product Code", "Added QTY"]).to_csv(STOCK_FILE, index=False)
                    df_st = pd.read_csv(STOCK_FILE)
        except:
            pass

    return pd.read_csv(PROD_FILE), pd.read_csv(MAP_FILE), pd.read_csv(SALES_FILE), df_st

df_prod, df_map, df_sales, df_stock = load_data()

def get_actual_inventory(start_date=None, end_date=None):
    df_p, df_m, df_sa, df_st = load_data()
    inward_stock = df_p.set_index('Product Code')['QTY'].to_dict()
    
    if not df_st.empty and start_date and end_date:
        try:
            df_st['Parsed_Date'] = pd.to_datetime(df_st['Date & Time']).dt.date
            df_st = df_st[(df_st['Parsed_Date'] >= start_date) & (df_st['Parsed_Date'] <= end_date)]
        except: pass

    for _, row in df_st.iterrows():
        p_code = row['Product Code']
        if p_code in inward_stock: inward_stock[p_code] += row['Added QTY']
            
    if not df_sa.empty and start_date and end_date:
        try:
            df_sa['Parsed_Date'] = pd.to_datetime(df_sa['Date']).dt.date
            df_sa = df_sa[(df_sa['Parsed_Date'] >= start_date) & (df_sa['Parsed_Date'] <= end_date)]
        except: pass

    sold_stock = {p_code: 0 for p_code in df_p['Product Code'].values}
    for _, sale in df_sa.iterrows():
        c_sku = sale['Channel SKU']
        s_qty = int(sale['QTY']) if pd.notna(sale['QTY']) else 0
        mapping = df_m[df_m['Seller SKU on Channel'] == c_sku]
        if not mapping.empty:
            for _, map_row in mapping.iterrows():
                linked_sku = map_row['SKU Code']
                master_components = df_p[df_p['Product Code'] == linked_sku]
                if not master_components.empty:
                    for _, comp_row in master_components.iterrows():
                        comp_sku = comp_row['Component Product Code']
                        if comp_sku in sold_stock: sold_stock[comp_sku] += s_qty
                else:
                    if linked_sku in sold_stock: linked_sku in sold_stock; sold_stock[linked_sku] += s_qty
        else:
            if c_sku in sold_stock: sold_stock[c_sku] += s_qty

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

# ---- Sidebar Configuration Panel ----
st.sidebar.markdown("<h2 style='color:white; text-align:center;'>Vida Loca Hub</h2>", unsafe_allow_html=True)
st.sidebar.write("---")
menu = st.sidebar.radio("📌 CONTROL PANEL:", [
    "📊 Live Dashboard", 
    "📦 1. MASTER SKU Sheet", 
    "🔗 2. CHANEL SKU MAP Sheet",
    "📥 3. ADD INVENTORY Sheet", 
    "📤 4. SALE DATA Sheet"
])

# ==================== LIVE DASHBOARD ====================
if menu == "📊 Live Dashboard":
    st.markdown("<h1 style='color:#0f172a;'>📊 OMS Core Dashboard</h1>", unsafe_allow_html=True)
    today = date.today()
    start_d = st.sidebar.date_input("Start Date", date(today.year, 1, 1))
    end_d = st.sidebar.date_input("End Date", today)
    
    df_actual = get_actual_inventory(start_date=start_d, end_date=end_d)
    
    brands = ["All"] + list(df_actual['Brand'].dropna().unique())
    selected_brand = st.sidebar.selectbox("Filter by Brand Name", brands)
    if selected_brand != "All": df_actual = df_actual[df_actual['Brand'] == selected_brand]
        
    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1: st.markdown(f'<div class="metric-container card-blue"><div class="metric-title">Unique Master SKUs</div><div class="metric-value">{len(df_actual)}</div></div>', unsafe_allow_html=True)
    with m_col2: st.markdown(f'<div class="metric-container card-orange"><div class="metric-title">Units Sold</div><div class="metric-value">{int(df_actual["Total Sold QTY"].sum())}</div></div>', unsafe_allow_html=True)
    with m_col3: st.markdown(f'<div class="metric-container card-green"><div class="metric-title">Net Available Stock</div><div class="metric-value">{int(df_actual["Actual Balance Stock"].sum())}</div></div>', unsafe_allow_html=True)
    
    st.write("---")
    st.dataframe(df_actual[["Image URL", "Product Code", "Name", "Color", "Size", "Brand", "Type", "QTY", "Total Sold QTY", "Actual Balance Stock"]], column_config={"Image URL": st.column_config.ImageColumn("Preview")}, use_container_width=True, hide_index=True)

# ==================== 1. MASTER SKU SHEET ====================
elif menu == "📦 1. MASTER SKU Sheet":
    st.markdown("<h1>📦 Master Inventory Dataset</h1>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["📁 Bulk File Import (Excel/CSV)", "✍️ Manual Single Entry"])
    
    with tab1:
        uploaded_file = st.file_uploader("Choose File", type=["xlsx", "csv"])
        if uploaded_file is not None:
            bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            st.dataframe(bulk_df.head(), hide_index=True)
            if st.button("🚀 Process & Sync Master Data"):
                bulk_df.to_csv(PROD_FILE, index=False)
                st.success("Master dataset processed successfully!")
                st.rerun()
    with tab2:
        with st.form("master_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            cat = col1.text_input("Category Code", "KURTA")
            p_code = col2.text_input("Product Code (Master SKU)").upper().strip()
            name = col1.text_input("Product Display Description")
            color = col2.text_input("Color variant")
            size = col1.text_input("Size tag")
            brand = col2.text_input("Brand", "Vida Loca")
            p_type = col1.selectbox("Classification Type", ["SIMPLE", "BUNDLE"])
            comp_code = col2.text_input("Component Product Code")
            qty = col1.number_input("Opening Quantity", min_value=0, value=0)
            img_url = col2.text_input("Image Link URL")
            
            if st.form_submit_button("Append Product Record") and p_code:
                pd.DataFrame([[cat, p_code, name, p_code, color, size, brand, p_type, comp_code, qty, img_url]], columns=df_prod.columns).to_csv(PROD_FILE, mode='a', header=False, index=False)
                st.success("New SKU configuration committed!")
                st.rerun()
    st.dataframe(df_prod, use_container_width=True, hide_index=True)

# ==================== 2. CHANEL SKU MAP SHEET ====================
elif menu == "🔗 2. CHANEL SKU MAP Sheet":
    st.markdown("<h1>🔗 Channel Mapping Matrix</h1>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload Connection file", type=["xlsx", "csv"])
    if uploaded_file is not None:
        bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        if st.button("🚀 Sync Link Map Table"):
            bulk_df.to_csv(MAP_FILE, index=False)
            st.success("Mapping configuration linked!")
            st.rerun()
    st.dataframe(df_map, use_container_width=True, hide_index=True)

# ==================== 3. ADD INVENTORY SHEET (FULLY COPIED TRANSFORMATION) ====================
elif menu == "📥 3. ADD INVENTORY Sheet":
    st.markdown("<h1>📥 Size-Matrix Stock Inward Load</h1>", unsafe_allow_html=True)
    st.info("⏰ Note: This inventory list automatically resets and flushes out every day at 12:00 PM.")
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Group master SKUs by their base design model to clean prefix logic
    unique_base_designs = sorted(list(df_prod['Product Code'].dropna().unique()))
    
    selected_design = st.selectbox("🎯 Select base Product Code Model", unique_base_designs)
    
    # Fetch details of selected product to display photo/specs live
    prod_meta = df_prod[df_prod['Product Code'] == selected_design]
    if not prod_meta.empty:
        col_img, col_det = st.columns([1, 4])
        img_val = prod_meta['Image URL'].iloc[0]
        if pd.notna(img_val) and str(img_val).strip() != "":
            col_img.image(img_val, width=100)
        col_det.write(f"**Name:** {prod_meta['Name'].iloc[0]} | **Color:** {prod_meta['Color'].iloc[0]} | **Brand:** {prod_meta['Brand'].iloc[0]}")
    
    st.write("---")
    st.markdown("### 🔢 Fill Inventory Quantity Size-wise:")
    
    # Elegant Horizontal Matrix Design layout matching exactly your grid choice
    size_cols = st.columns(7)
    q_xs = size_cols[0].number_input("XS QTY", min_value=0, value=0, step=1)
    q_s  = size_cols[1].number_input("S QTY", min_value=0, value=0, step=1)
    q_m  = size_cols[2].number_input("M QTY", min_value=0, value=0, step=1)
    q_l  = size_cols[3].number_input("L QTY", min_value=0, value=0, step=1)
    q_xl = size_cols[4].number_input("XL QTY", min_value=0, value=0, step=1)
    q_2xl = size_cols[5].number_input("XXL QTY", min_value=0, value=0, step=1)
    q_3xl = size_cols[6].number_input("3XL QTY", min_value=0, value=0, step=1)
    
    if st.button("🚀 Submit Multi-Size Batch Allocation"):
        allocations = {
            "XS": q_xs, "S": q_s, "M": q_m, "L": q_l, "XL": q_xl, "XXL": q_2xl, "3XL": q_3xl
        }
        
        added_entries = 0
        for sz, qty_input in allocations.items():
            if qty_input > 0:
                # Append size keyword to search match row accurately
                target_sku_variant = f"{selected_design}-{sz}" if "-" not in selected_design else selected_design
                
                # If product catalog treats design raw code directly, fall back smoothly
                pd.DataFrame([[current_time, target_sku_variant, qty_input]], columns=df_stock.columns).to_csv(STOCK_FILE, mode='a', header=False, index=False)
                added_entries += 1
                
        if added_entries > 0:
            st.success(f"Successfully processed {added_entries} size updates into Live Inventory Database!")
            st.rerun()
            
    st.write("---")
    st.subheader("📋 Today's Pending Processing Log (Flushes at 12:00 PM)")
    st.dataframe(df_stock, use_container_width=True, hide_index=True)

# ==================== 4. SALE DATA SHEET ====================
elif menu == "📤 4. SALE DATA Sheet":
    st.markdown("<h1>📤 Channel Sales Manifest</h1>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload manifest logs file", type=["xlsx", "csv"])
    if uploaded_file is not None:
        bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        if st.button("🚀 Deduct Mapped Inventory levels"):
            bulk_df.to_csv(SALES_FILE, index=False)
            st.success("Order evaluation complete!")
            st.rerun()
    st.dataframe(df_sales, use_container_width=True, hide_index=True)
