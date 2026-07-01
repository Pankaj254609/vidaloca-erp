import streamlit as st
import pandas as pd
import os
import random
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
        pd.DataFrame(columns=["Date", "Channel SKU", "Type", "BRAND", "QTY"]).to_csv(SALES_FILE, index=False)
    if not os.path.exists(STOCK_FILE):
        pd.DataFrame(columns=["Date & Time", "Product Code", "Added QTY"]).to_csv(STOCK_FILE, index=False)

    df_p = pd.read_csv(PROD_FILE)
    if "Image URL" not in df_p.columns:
        df_p["Image URL"] = ""
        df_p.to_csv(PROD_FILE, index=False)

    # Safe reading of Sales file to handle Parser Errors gracefully
    try:
        df_sa = pd.read_csv(SALES_FILE, on_bad_lines='skip')
    except:
        df_sa = pd.DataFrame(columns=["Date", "Channel SKU", "Type", "BRAND", "QTY"])
        df_sa.to_csv(SALES_FILE, index=False)

    return df_p, pd.read_csv(MAP_FILE), df_sa, pd.read_csv(STOCK_FILE)

# Global initial data load
df_prod, df_map, df_sales, df_stock = load_data()

# Helper functions
def find_column(df, possible_names, default_name):
    for col in df.columns:
        if str(col).strip().lower() in [p.lower() for p in possible_names]:
            return col
    for col in df.columns:
        for p in possible_names:
            if p.lower() in str(col).strip().lower():
                return col
    return default_name

def clean_sku(val):
    if pd.isna(val): return ""
    s = str(val).strip().upper()
    if s.endswith('.0'): s = s[:-2]
    return s

def get_actual_inventory(start_date=None, end_date=None, selected_brand="All", ignore_date=False):
    df_p, df_m, df_sa, df_st = load_data()
    
    p_code_col = find_column(df_p, ["Product Code", "Master SKU", "SKU"], "Product Code")
    p_brand_col = find_column(df_p, ["Brand"], "Brand")
    p_qty_col = find_column(df_p, ["QTY", "Opening Quantity"], "QTY")
    p_scan_col = find_column(df_p, ["Scan Identifier", "Barcode"], "Scan Identifier")
    p_comp_col = find_column(df_p, ["Component Product Code", "Component SKU"], "Component Product Code")
    p_type_col = find_column(df_p, ["Type", "Classification Type"], "Type")
    
    if selected_brand != "All" and p_brand_col in df_p.columns:
        df_p = df_p[df_p[p_brand_col] == selected_brand]
        
    inward_stock = {}
    if p_code_col in df_p.columns and p_qty_col in df_p.columns:
        for _, r in df_p.iterrows():
            code = clean_sku(r[p_code_col])
            try: inward_stock[code] = int(r[p_qty_col]) if pd.notna(r[p_qty_col]) else 0
            except: inward_stock[code] = 0
                
    sold_stock = {code: 0 for code in inward_stock.keys()}
    
    # ADD INVENTORY
    st_date_col = find_column(df_st, ["Date & Time", "Date"], "Date & Time")
    st_code_col = find_column(df_st, ["Product Code", "SKU"], "Product Code")
    st_qty_col = find_column(df_st, ["Added QTY", "QTY"], "Added QTY")
    
    if not df_st.empty and st_date_col in df_st.columns and not ignore_date:
        try:
            df_st['Parsed_Date'] = pd.to_datetime(df_st[st_date_col], errors='coerce').dt.date
            if start_date and end_date:
                df_st = df_st[(df_st['Parsed_Date'] >= start_date) & (df_st['Parsed_Date'] <= end_date)]
        except: pass

    if st_code_col in df_st.columns and st_qty_col in df_st.columns:
        for _, row in df_st.iterrows():
            p_code = clean_sku(row[st_code_col])
            try: q = int(row[st_qty_col]) if pd.notna(row[st_qty_col]) else 0
            except: q = 0
            if p_code in inward_stock: inward_stock[p_code] += q

    # SALE DATA
    sa_date_col = find_column(df_sa, ["Date", "Order Date", "Sale Date"], "Date")
    sa_sku_col = find_column(df_sa, ["Channel SKU", "SKU", "Seller SKU", "Item SKU"], "Channel SKU")
    sa_qty_col = find_column(df_sa, ["QTY", "Quantity", "Qty Sold"], "QTY")
    sa_type_col = find_column(df_sa, ["Type", "SKU Type"], "Type")
    
    if not df_sa.empty and sa_date_col in df_sa.columns and not ignore_date:
        try:
            df_sa['Parsed_Date'] = pd.to_datetime(df_sa[sa_date_col], errors='coerce').dt.date
            if start_date and end_date:
                df_sa = df_sa[(df_sa['Parsed_Date'] >= start_date) & (df_sa['Parsed_Date'] <= end_date)]
        except: pass

    m_chan_col = find_column(df_m, ["Seller SKU on Channel", "Channel SKU", "Seller SKU"], "Seller SKU on Channel")
    m_master_col = find_column(df_m, ["SKU Code", "Master SKU"], "SKU Code")
    
    chanel_map = {}
    if not df_m.empty and m_chan_col in df_m.columns and m_master_col in df_m.columns:
        for _, m_row in df_m.iterrows():
            c_sku = clean_sku(m_row[m_chan_col])
            s_code = clean_sku(m_row[m_master_col])
            if c_sku: chanel_map[c_sku] = s_code

    full_master = pd.read_csv(PROD_FILE)
    fm_code_col = find_column(full_master, ["Product Code", "Master SKU", "SKU"], "Product Code")
    fm_scan_col = find_column(full_master, ["Scan Identifier", "Barcode"], "Scan Identifier")
    fm_comp_col = find_column(full_master, ["Component Product Code", "Component SKU"], "Component Product Code")

    if not df_sa.empty and sa_sku_col in df_sa.columns and sa_qty_col in df_sa.columns:
        for _, sale in df_sa.iterrows():
            sku_input = clean_sku(sale[sa_sku_col])
            try: s_qty = int(sale[sa_qty_col]) if pd.notna(sale[sa_qty_col]) else 0
            except: s_qty = 0
            
            sale_type = str(sale[sa_type_col]).strip().upper() if sa_type_col in df_sa.columns and pd.notna(sale[sa_type_col]) else "SINGLE"

            if not sku_input: continue

            if sale_type in ["BUNDAL", "BUNDLE"]:
                if fm_scan_col in full_master.columns and fm_comp_col in full_master.columns:
                    matches = full_master[full_master[fm_scan_col].astype(str).str.strip().str.upper() == sku_input]
                    match_count = 0
                    for _, m_row in matches.iterrows():
                        comp_sku = clean_sku(m_row[fm_comp_col])
                        if comp_sku in sold_stock: sold_stock[comp_sku] += s_qty
                        match_count += 1
                        if match_count == 2: break
            else:
                found_sku = chanel_map.get(sku_input, sku_input)
                if found_sku in sold_stock:
                    sold_stock[found_sku] += s_qty
                else:
                    if fm_comp_col in full_master.columns and fm_code_col in full_master.columns:
                        comp_matches = full_master[full_master[fm_comp_col].astype(str).str.strip().str.upper() == found_sku]
                        for _, c_row in comp_matches.iterrows():
                            c_code = clean_sku(c_row[fm_code_col])
                            if c_code in sold_stock: sold_stock[c_code] += s_qty
                    if sku_input in sold_stock:
                        sold_stock[sku_input] += s_qty

    total_inward_list = []
    total_sold_list = []
    balance_list = []
    
    for _, row in df_p.iterrows():
        code = clean_sku(row[p_code_col])
        total_in = inward_stock.get(code, 0)
        total_sold = sold_stock.get(code, 0)
        total_inward_list.append(total_in)
        total_sold_list.append(total_sold)
        balance_list.append(total_in - total_sold)
        
    df_p['Total Inward Stock'] = total_inward_list
    df_p['Total Sold QTY'] = total_sold_list
    df_p['Actual Balance Stock'] = balance_list
    return df_p

def get_datewise_summary(start_date, end_date, selected_brand="All", ignore_date=False):
    df_p, df_m, df_sa, df_st = load_data()
    p_code_col = find_column(df_p, ["Product Code", "Master SKU"], "Product Code")
    p_brand_col = find_column(df_p, ["Brand"], "Brand")
    
    if selected_brand != "All" and p_brand_col in df_p.columns:
        df_p = df_p[df_p[p_brand_col] == selected_brand]
    allowed_products = set(df_p[p_code_col].astype(str).str.strip().str.upper().values) if p_code_col in df_p.columns else set()
    
    inward_by_date = {}
    st_date_col = find_column(df_st, ["Date & Time", "Date"], "Date & Time")
    st_code_col = find_column(df_st, ["Product Code"], "Product Code")
    st_qty_col = find_column(df_st, ["Added QTY"], "Added QTY")
    
    if not df_st.empty and st_date_col in df_st.columns:
        try:
            df_st['Date_Only'] = pd.to_datetime(df_st[st_date_col], errors='coerce').dt.date
            df_filtered_st = df_st[df_st['Date_Only'].notna()]
            if not ignore_date:
                df_filtered_st = df_filtered_st[(df_filtered_st['Date_Only'] >= start_date) & (df_filtered_st['Date_Only'] <= end_date)]
            for _, row in df_filtered_st.iterrows():
                p_code = clean_sku(row[st_code_col])
                if p_code in allowed_products:
                    d_only = row['Date_Only']
                    inward_by_date[d_only] = inward_by_date.get(d_only, 0) + int(row[st_qty_col])
        except: pass

    sales_by_date = {}
    sa_date_col = find_column(df_sa, ["Date", "Order Date"], "Date")
    sa_sku_col = find_column(df_sa, ["Channel SKU", "SKU"], "Channel SKU")
    sa_qty_col = find_column(df_sa, ["QTY", "Quantity"], "QTY")
    sa_type_col = find_column(df_sa, ["Type"], "Type")
    
    if not df_sa.empty and sa_date_col in df_sa.columns:
        try:
            df_sa['Date_Only'] = pd.to_datetime(df_sa[sa_date_col], errors='coerce').dt.date
            df_filtered_sa = df_sa[df_sa['Date_Only'].notna()]
            if not ignore_date:
                df_filtered_sa = df_filtered_sa[(df_filtered_sa['Date_Only'] >= start_date) & (df_filtered_sa['Date_Only'] <= end_date)]
            
            m_chan_col = find_column(df_m, ["Seller SKU on Channel", "Channel SKU"], "Seller SKU on Channel")
            m_master_col = find_column(df_m, ["SKU Code"], "SKU Code")
            
            chanel_map = {}
            if not df_m.empty and m_chan_col in df_m.columns and m_master_col in df_m.columns:
                for _, m_row in df_m.iterrows():
                    chanel_map[clean_sku(m_row[m_chan_col])] = clean_sku(m_row[m_master_col])

            full_master = pd.read_csv(PROD_FILE)
            fm_scan_col = find_column(full_master, ["Scan Identifier"], "Scan Identifier")

            for _, sale in df_filtered_sa.iterrows():
                sku_input = clean_sku(sale[sa_sku_col])
                try: s_qty = int(sale[sa_qty_col]) if pd.notna(sale[sa_qty_col]) else 0
                except: s_qty = 0
                d_only = sale['Date_Only']
                sale_type = str(sale[sa_type_col]).strip().upper() if sa_type_col in df_sa.columns and pd.notna(sale[sa_type_col]) else "SINGLE"
                
                is_valid = False
                if sale_type in ["BUNDAL", "BUNDLE"]:
                    if fm_scan_col in full_master.columns:
                        matches = full_master[full_master[fm_scan_col].astype(str).str.strip().str.upper() == sku_input]
                        if not matches.empty: is_valid = True
                else:
                    target = chanel_map.get(sku_input, sku_input)
                    if target in allowed_products: is_valid = True
                        
                if is_valid:
                    sales_by_date[d_only] = sales_by_date.get(d_only, 0) + s_qty
        except: pass

    all_dates = sorted(list(set(list(inward_by_date.keys()) + list(sales_by_date.keys()))))
    summary_records = []
    for d in all_dates:
        summary_records.append({
            "Date": d.strftime("%Y-%m-%d"),
            "Total Inward QTY": inward_by_date.get(d, 0),
            "Total Sales QTY": sales_by_date.get(d, 0)
        })
    return pd.DataFrame(summary_records)

# --- Mock Channel Sync Feature ---
def simulate_live_channel_orders():
    df_p, df_m, _, _ = load_data()
    if df_p.empty:
        return "Master SKU list is empty! Please add products first."
    
    mock_orders = []
    p_code_col = find_column(df_p, ["Product Code", "Master SKU", "SKU"], "Product Code")
    available_skus = df_p[p_code_col].dropna().tolist() if p_code_col in df_p.columns else []
    if not available_skus:
        return "No Product Codes available to simulate."
        
    num_orders = random.randint(2, 5)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    m_master_col = find_column(df_m, ["SKU Code", "Master SKU"], "SKU Code")
    m_chan_col = find_column(df_m, ["Seller SKU on Channel", "Channel SKU", "Seller SKU"], "Seller SKU on Channel")

    for _ in range(num_orders):
        chosen_sku = random.choice(available_skus)
        
        if not df_m.empty and m_master_col in df_m.columns and m_chan_col in df_m.columns and random.random() > 0.4:
            mapped_options = df_m[df_m[m_master_col].astype(str).str.upper() == str(chosen_sku).upper()]
            if not mapped_options.empty:
                sku_to_log = random.choice(mapped_options[m_chan_col].tolist())
            else:
                sku_to_log = chosen_sku
        else:
            sku_to_log = chosen_sku
            
        qty = random.randint(1, 3)
        brand_val = "VIDA LOCA"
        mock_orders.append([today_str, sku_to_log, "SINGLE", brand_val, qty])
    
    # Save safely line-by-line avoiding structural breaks
    try:
        df_old_sales = pd.read_csv(SALES_FILE, on_bad_lines='skip')
    except:
        df_old_sales = pd.DataFrame(columns=["Date", "Channel SKU", "Type", "BRAND", "QTY"])
        
    df_new_sales = pd.DataFrame(mock_orders, columns=["Date", "Channel SKU", "Type", "BRAND", "QTY"])
    df_combined = pd.concat([df_old_sales, df_new_sales], ignore_index=True)
    df_combined.to_csv(SALES_FILE, index=False)
    
    return f"Successfully fetched {num_orders} live orders from Mock Marketplaces API!"

# ---- Sidebar Panel ----
st.sidebar.markdown("<h2 style='color:white; text-align:center;'>Vida Loca Hub</h2>", unsafe_allow_html=True)
st.sidebar.write("---")
menu = st.sidebar.radio("📌 CONTROL PANEL:", [
    "📊 Live Dashboard", 
    "🔄 Live Channels Sync",
    "📦 1. MASTER SKU Sheet", 
    "🔗 2. CHANEL SKU MAP Sheet",
    "📥 3. ADD INVENTORY Sheet", 
    "📤 4. SALE DATA Sheet"
])

df_prod, df_map, df_sales, df_stock = load_data()

# ==================== LIVE DASHBOARD ====================
if menu == "📊 Live Dashboard":
    st.markdown("<h1 style='color:#0f172a;'>📊 OMS Core Dashboard</h1>", unsafe_allow_html=True)
    today = date.today()
    start_d = st.sidebar.date_input("Start Date", date(today.year, 1, 1))
    end_d = st.sidebar.date_input("End Date", today)
    
    ignore_date = st.sidebar.checkbox("Ignore Date Filter (Show All-Time Sales)", value=True)
    
    all_brands = ["All"] + list(df_prod['Brand'].dropna().unique()) if not df_prod.empty else ["All"]
    selected_brand = st.sidebar.selectbox("Filter by Brand Name", all_brands)
    
    df_actual = get_actual_inventory(start_date=start_d, end_date=end_d, selected_brand=selected_brand, ignore_date=ignore_date)
        
    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1: 
        st.markdown(f'<div class="metric-container card-blue"><div class="metric-title">Total Inward Stock</div><div class="metric-value">{int(df_actual["Total Inward Stock"].sum())}</div></div>', unsafe_allow_html=True)
    with m_col2: 
        st.markdown(f'<div class="metric-container card-orange"><div class="metric-title">Total Sale QTY</div><div class="metric-value">{int(df_actual["Total Sold QTY"].sum())}</div></div>', unsafe_allow_html=True)
    with m_col3: 
        st.markdown(f'<div class="metric-container card-green"><div class="metric-title">Actual Balance Stock</div><div class="metric-value">{int(df_actual["Actual Balance Stock"].sum())}</div></div>', unsafe_allow_html=True)
    
    st.write("---")
    st.subheader("📅 Date-wise Stock & Sales Summary")
    df_date_summary = get_datewise_summary(start_d, end_d, selected_brand=selected_brand, ignore_date=ignore_date)
    if not df_date_summary.empty:
        st.dataframe(df_date_summary, use_container_width=True, hide_index=True)
    else:
        st.info("No logs found for the selected configuration.")

    st.write("---")
    st.subheader("📋 Inventory Ledger Table")
    
    show_cols = []
    img_col = find_column(df_actual, ["Image URL", "Preview"], "Image URL")
    code_col = find_column(df_actual, ["Product Code", "Master SKU"], "Product Code")
    name_col = find_column(df_actual, ["Name", "Description"], "Name")
    color_col = find_column(df_actual, ["Color"], "Color")
    size_col = find_column(df_actual, ["Size"], "Size")
    brand_col = find_column(df_actual, ["Brand"], "Brand")
    type_col = find_column(df_actual, ["Type"], "Type")
    
    for c in [img_col, code_col, name_col, color_col, size_col, brand_col, type_col, "Total Inward Stock", "Total Sold QTY", "Actual Balance Stock"]:
        if c in df_actual.columns: show_cols.append(c)
            
    st.dataframe(df_actual[show_cols], column_config={img_col: st.column_config.ImageColumn("Preview")}, use_container_width=True, hide_index=True)

# ==================== LIVE CHANNELS SYNC (MOCK UNICOMMERCE) ====================
elif menu == "🔄 Live Channels Sync":
    st.markdown("<h1>🔄 Live Channel Marketplace Integrations</h1>", unsafe_allow_html=True)
    st.write("This simulation mimics Unicommerce APIs pull endpoints to fetch orders from **Amazon, Flipkart, Meesho, Myntra, and Snapdeal**.")
    
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.info("🟢 Amazon SP-API Status: Connected (Mock)")
    c2.info("🟢 Flipkart API Status: Connected (Mock)")
    c3.info("🟢 Meesho API Status: Connected (Mock)")
    c4.info("🟢 Myntra API Status: Connected (Mock)")
    c5.info("🟢 Snapdeal API Status: Connected (Mock)")
    
    st.write("---")
    st.subheader("Simulate Real-time Order Engine")
    if st.button("🔌 Run Unicommerce Sync Engine (Fetch Orders)"):
        with st.spinner("Calling marketplace endpoints and pulling new sales data..."):
            status_msg = simulate_live_channel_orders()
            st.success(status_msg)
            st.toast("Stock updated instantly across channels!")
            
    st.write("---")
    st.subheader("Current Synced Sales Manifest Logs")
    try:
        df_sales_view = pd.read_csv(SALES_FILE, on_bad_lines='skip')
    except:
        df_sales_view = pd.DataFrame(columns=["Date", "Channel SKU", "Type", "BRAND", "QTY"])
    st.dataframe(df_sales_view.tail(15), use_container_width=True, hide_index=True)

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

# ==================== 3. ADD INVENTORY SHEET ====================
elif menu == "📥 3. ADD INVENTORY Sheet":
    st.markdown("<h1>📥 Stock Inward Ledger Panel</h1>", unsafe_allow_html=True)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    inv_tab1, inv_tab2 = st.tabs(["📁 1. Bulk Inventory Upload (Excel/CSV)", "✍️ 2. Name & Color Matrix Entry"])

    with inv_tab1:
        st.subheader("Upload Multi-product Stock Inward File")
        uploaded_inv_file = st.file_uploader("Choose Excel or CSV manifest file", type=["xlsx", "csv"], key="bulk_inv_upload")
        if uploaded_inv_file is not None:
            bulk_inv_df = pd.read_csv(uploaded_inv_file) if uploaded_inv_file.name.endswith('.csv') else pd.read_excel(uploaded_inv_file)
            if "Date & Time" not in bulk_inv_df.columns:
                bulk_inv_df["Date & Time"] = current_time
            else:
                bulk_inv_df["Date & Time"] = bulk_inv_df["Date & Time"].fillna(current_time)
            st.dataframe(bulk_inv_df.head(), hide_index=True)
            if st.button("🚀 Process Bulk Stock Load"):
                final_bulk_inv = bulk_inv_df[["Date & Time", "Product Code", "Added QTY"]]
                final_bulk_inv.to_csv(STOCK_FILE, mode='a', header=False, index=False)
                st.success(f"Successfully processed {len(final_bulk_inv)} items into Live Stock!")
                st.rerun()

    with inv_tab2:
        unique_names = sorted(list(df_prod['Name'].dropna().unique())) if not df_prod.empty else []
        selected_name = st.selectbox("👗 Select Product Name / Description", unique_names, key="name_selector")
        
        filtered_by_name = df_prod[df_prod['Name'] == selected_name]
        available_colors = sorted(list(filtered_by_name['Color'].dropna().unique()))
        selected_color = st.selectbox("🎨 Select Color", available_colors, key="color_selector")
        
        final_meta = filtered_by_name[filtered_by_name['Color'] == selected_color]
        
        if not final_meta.empty:
            st.write("---")
            col_img, col_det = st.columns([1, 4])
            img_val = final_meta['Image URL'].iloc[0]
            if pd.notna(img_val) and str(img_val).strip() != "":
                col_img.image(img_val, width=120)
            col_det.write(f"**Selected Product:** {selected_name}  \n**Color Theme:** {selected_color}  \n**Brand:** {final_meta['Brand'].iloc[0]}")
            
            base_code_sample = final_meta['Product Code'].iloc[0]
            base_design_prefix = base_code_sample.split('-')[0] if '-' in str(base_code_sample) else base_code_sample
            
            st.write("---")
            st.markdown("### 🔢 Fill Inventory Quantity Size-wise:")
            
            size_cols = st.columns(7)
            q_xs = size_cols[0].number_input("XS QTY", min_value=0, value=0, step=1, key="xs")
            q_s  = size_cols[1].number_input("S QTY", min_value=0, value=0, step=1, key="s")
            q_m  = size_cols[2].number_input("M QTY", min_value=0, value=0, step=1, key="m")
            q_l  = size_cols[3].number_input("L QTY", min_value=0, value=0, step=1, key="l")
            q_xl = size_cols[4].number_input("XL QTY", min_value=0, value=0, step=1, key="xl")
            q_2xl = size_cols[5].number_input("XXL QTY", min_value=0, value=0, step=1, key="xxl")
            q_3xl = size_cols[6].number_input("3XL QTY", min_value=0, value=0, step=1, key="3xl")
            
            if st.button("🚀 Submit Multi-Size Batch Allocation"):
                allocations = {"XS": q_xs, "S": q_s, "M": q_m, "L": q_l, "XL": q_xl, "XXL": q_2xl, "3XL": q_3xl}
                added_entries = 0
                for sz, qty_input in allocations.items():
                    if qty_input > 0:
                        target_sku_variant = f"{base_design_prefix}-{sz}"
                        pd.DataFrame([[current_time, target_sku_variant, qty_input]], columns=df_stock.columns).to_csv(STOCK_FILE, mode='a', header=False, index=False)
                        added_entries += 1
                if added_entries > 0:
                    st.success(f"Processed {added_entries} size updates into Live Inventory Database!")
                    st.rerun()
        else:
            st.warning("No matching SKU found for this combination in Master Sheet.")
                
    st.write("---")
    st.subheader("📋 Total Inward Processing History Log")
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
    try:
        df_sales_final = pd.read_csv(SALES_FILE, on_bad_lines='skip')
    except:
        df_sales_final = pd.DataFrame(columns=["Date", "Channel SKU", "Type", "BRAND", "QTY"])
    st.dataframe(df_sales_final, use_container_width=True, hide_index=True)
