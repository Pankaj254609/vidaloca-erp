import streamlit as st
import pandas as pd
import random
from datetime import datetime, date
from supabase import create_client, Client

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

# --- SUPABASE CONNECTION ---
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Supabase Client Connection Error: {e}")

# --- LIVE DATABASE DATA LOADING ---
def load_data_cached():
    # 1. Master SKU Fetch
    try:
        res_p = supabase.table("master_sku").select("*").execute()
        df_p = pd.DataFrame(res_p.data)
        if not df_p.empty:
            actual_cols = ["category_code", "product_code", "name", "scan_identifier", "color", "size", "brand", "type", "component_product_code", "qty", "image_url"]
            df_p = df_p[[c for c in actual_cols if c in df_p.columns]]
            df_p.columns = ["Category Code", "Product Code", "Name", "Scan Identifier", "Color", "Size", "Brand", "Type", "Component Product Code", "QTY", "Image URL"][:len(df_p.columns)]
    except Exception as e:
        df_p = pd.DataFrame()
        
    if df_p.empty:
        df_p = pd.DataFrame(columns=["Category Code", "Product Code", "Name", "Scan Identifier", "Color", "Size", "Brand", "Type", "Component Product Code", "QTY", "Image URL"])

    # 2. Mapping Matrix Fetch
    try:
        res_m = supabase.table("channel_sku_map").select("*").execute()
        df_m = pd.DataFrame(res_m.data)
        if not df_m.empty:
            df_m = df_m.drop(columns=["id", "created_at"], errors="ignore")
            df_m.columns = ["Seller SKU on Channel", "SKU Code", "channelName", "PACK OF", "BRAND"][:len(df_m.columns)]
    except Exception as e:
        df_m = pd.DataFrame()
        
    if df_m.empty:
        df_m = pd.DataFrame(columns=["Seller SKU on Channel", "SKU Code", "channelName", "PACK OF", "BRAND"])

    # 3. Sales Fetch
    try:
        res_sa = supabase.table("sale_data").select("*").execute()
        df_sa = pd.DataFrame(res_sa.data)
        if not df_sa.empty:
            df_sa = df_sa.drop(columns=["id", "created_at"], errors="ignore")
            df_sa.columns = ["Date", "Channel SKU", "Type", "BRAND", "QTY"][:len(df_sa.columns)]
    except Exception as e:
        df_sa = pd.DataFrame()
        
    if df_sa.empty:
        df_sa = pd.DataFrame(columns=["Date", "Channel SKU", "Type", "BRAND", "QTY"])

    # 4. Stock Fetch
    try:
        res_st = supabase.table("add_inventory").select("*").execute()
        df_st = pd.DataFrame(res_st.data)
        if not df_st.empty:
            df_st = df_st.drop(columns=["id", "created_at"], errors="ignore")
            df_st.columns = ["Date & Time", "Product Code", "Added QTY"][:len(df_st.columns)]
    except Exception as e:
        df_st = pd.DataFrame()
        
    if df_st.empty:
        df_st = pd.DataFrame(columns=["Date & Time", "Product Code", "Added QTY"])

    return df_p, df_m, df_sa, df_st

def clear_app_cache():
    st.cache_data.clear()

def clean_sku(val):
    if pd.isna(val): return ""
    s = str(val).strip().upper()
    if s.endswith('.0'): s = s[:-2]
    return s

# --- INVENTORY CALCULATION ---
def get_actual_inventory_cached(start_date=None, end_date=None, selected_brand="All", ignore_date=False):
    df_p, df_m, df_sa, df_st = load_data_cached()
    
    p_code_col = "Product Code"
    p_brand_col = "Brand"
    p_qty_col = "QTY"
    p_scan_col = "Scan Identifier"
    p_comp_col = "Component Product Code"
    
    if selected_brand != "All" and p_brand_col in df_p.columns:
        df_p = df_p[df_p[p_brand_col].astype(str).str.upper() == selected_brand.upper()]
        
    inward_stock = {}
    if p_code_col in df_p.columns and p_qty_col in df_p.columns:
        for _, r in df_p.iterrows():
            code = clean_sku(r[p_code_col])
            try: inward_stock[code] = int(r[p_qty_col]) if pd.notna(r[p_qty_col]) else 0
            except: inward_stock[code] = 0
                
    sold_stock = {code: 0 for code in inward_stock.keys()}
    
    if not df_st.empty and not ignore_date:
        try:
            df_st['Parsed_Date'] = pd.to_datetime(df_st["Date & Time"], errors='coerce').dt.date
            if start_date and end_date:
                df_st = df_st[(df_st['Parsed_Date'] >= start_date) & (df_st['Parsed_Date'] <= end_date)]
        except: pass

    if "Product Code" in df_st.columns and "Added QTY" in df_st.columns:
        for _, row in df_st.iterrows():
            p_code = clean_sku(row["Product Code"])
            try: q = int(row["Added QTY"]) if pd.notna(row["Added QTY"]) else 0
            except: q = 0
            if p_code in inward_stock: inward_stock[p_code] += q

    if not df_sa.empty:
        try:
            df_sa['Parsed_Date'] = pd.to_datetime(df_sa["Date"], errors='coerce').dt.date
            if not ignore_date and start_date and end_date:
                df_sa = df_sa[(df_sa['Parsed_Date'] >= start_date) & (df_sa['Parsed_Date'] <= end_date)]
            if selected_brand != "All" and "BRAND" in df_sa.columns:
                df_sa = df_sa[df_sa["BRAND"].astype(str).str.upper() == selected_brand.upper()]
        except: pass

    chanel_map = {}
    if not df_m.empty:
        for _, m_row in df_m.iterrows():
            c_sku = clean_sku(m_row["Seller SKU on Channel"])
            s_code = clean_sku(m_row["SKU Code"])
            if c_sku: chanel_map[c_sku] = s_code

    full_master = df_p.copy()

    if not df_sa.empty:
        for _, sale in df_sa.iterrows():
            sku_input = clean_sku(sale["Channel SKU"])
            try: s_qty = int(sale["QTY"]) if pd.notna(sale["QTY"]) else 0
            except: s_qty = 0
            
            sale_type = str(sale["Type"]).strip().upper() if pd.notna(sale["Type"]) else "SINGLE"

            if not sku_input: continue

            if sale_type in ["BUNDAL", "BUNDLE"]:
                if p_scan_col in full_master.columns and p_comp_col in full_master.columns:
                    matches = full_master[full_master[p_scan_col].astype(str).str.strip().str.upper() == sku_input]
                    match_count = 0
                    for _, m_row in matches.iterrows():
                        comp_sku = clean_sku(m_row[p_comp_col])
                        if comp_sku in sold_stock: sold_stock[comp_sku] += s_qty
                        match_count += 1
                        if match_count == 2: break
            else:
                found_sku = chanel_map.get(sku_input, sku_input)
                if found_sku in sold_stock:
                    sold_stock[found_sku] += s_qty
                else:
                    if p_comp_col in full_master.columns and p_code_col in full_master.columns:
                        comp_matches = full_master[full_master[p_comp_col].astype(str).str.strip().str.upper() == found_sku]
                        for _, c_row in comp_matches.iterrows():
                            c_code = clean_sku(c_row[p_code_col])
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

def get_datewise_summary_cached(start_date, end_date, selected_brand="All", ignore_date=False):
    df_p, df_m, df_sa, df_st = load_data_cached()
    
    inward_by_date = {}
    if not df_st.empty:
        try:
            df_st['Date_Only'] = pd.to_datetime(df_st["Date & Time"], errors='coerce').dt.date
            df_filtered_st = df_st[df_st['Date_Only'].notna()]
            if not ignore_date:
                df_filtered_st = df_filtered_st[(df_filtered_st['Date_Only'] >= start_date) & (df_filtered_st['Date_Only'] <= end_date)]
            for _, row in df_filtered_st.iterrows():
                d_only = row['Date_Only']
                try: added_qty = int(row["Added QTY"])
                except: added_qty = 0
                inward_by_date[d_only] = inward_by_date.get(d_only, 0) + added_qty
        except: pass

    sales_by_date = {}
    if not df_sa.empty:
        try:
            df_sa['Date_Only'] = pd.to_datetime(df_sa["Date"], errors='coerce').dt.date
            df_filtered_sa = df_sa[df_sa['Date_Only'].notna()]
            
            if not ignore_date:
                df_filtered_sa = df_filtered_sa[(df_filtered_sa['Date_Only'] >= start_date) & (df_filtered_sa['Date_Only'] <= end_date)]
            
            if selected_brand != "All" and "BRAND" in df_filtered_sa.columns:
                df_filtered_sa = df_filtered_sa[df_filtered_sa["BRAND"].astype(str).str.upper() == selected_brand.upper()]
            
            for _, sale in df_filtered_sa.iterrows():
                try: s_qty = int(sale["QTY"]) if pd.notna(sale["QTY"]) else 0
                except: s_qty = 0
                d_only = sale['Date_Only']
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

def simulate_live_channel_orders():
    df_p, df_m, _, _ = load_data_cached()
    if df_p.empty: return "Master SKU list is empty!"
    
    available_skus = df_p["Product Code"].dropna().tolist()
    num_orders = random.randint(2, 5)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    mock_orders = []
    for _ in range(num_orders):
        chosen_sku = random.choice(available_skus)
        sku_to_log = chosen_sku
        if not df_m.empty and random.random() > 0.4:
            mapped_options = df_m[df_m["SKU Code"].astype(str).str.upper() == str(chosen_sku).upper()]
            if not mapped_options.empty:
                sku_to_log = random.choice(mapped_options["Seller SKU on Channel"].tolist())
            
        qty = random.randint(1, 3)
        mock_orders.append({
            "date": today_str, "channel_sku": sku_to_log, "type": "SINGLE", "brand": "VIDA LOCA", "qty": qty
        })
    
    if mock_orders:
        try:
            supabase.table("sale_data").insert(mock_orders).execute()
        except: pass
    clear_app_cache()
    return f"Successfully fetched {num_orders} live orders via Unicommerce Mock API directly into Database!"

# ---- Sidebar Panel ----
st.sidebar.markdown("<h2 style='color:white; text-align:center;'>Vida Loca Hub</h2>", unsafe_allow_html=True)
st.sidebar.write("---")
menu = st.sidebar.radio("📌 CONTROL PANEL:", [
    "📊 Live Dashboard", "🔄 Live Channels Sync", "📦 1. MASTER SKU Sheet", 
    "🔗 2. CHANEL SKU MAP Sheet", "📥 3. ADD INVENTORY Sheet", "📤 4. SALE DATA Sheet"
])

df_prod, df_map, df_sales, df_stock = load_data_cached()

# ==================== LIVE DASHBOARD ====================
if menu == "📊 Live Dashboard":
    st.markdown("<h1 style='color:#0f172a;'>📊 OMS Core Dashboard</h1>", unsafe_allow_html=True)
    today = date.today()
    start_d = st.sidebar.date_input("Start Date", date(today.year, 1, 1))
    end_d = st.sidebar.date_input("End Date", today)
    ignore_date = st.sidebar.checkbox("Ignore Date Filter (Show All-Time Sales)", value=True)
    
    # 1. Dynamic Brand Extraction direct Sales Table se (Strictly Case Insensitive)
    if not df_sales.empty and "BRAND" in df_sales.columns:
        all_brands = ["All"] + sorted(list(df_sales['BRAND'].dropna().astype(str).str.upper().unique()))
    elif not df_prod.empty and 'Brand' in df_prod.columns:
        all_brands = ["All"] + sorted(list(df_prod['Brand'].dropna().astype(str).str.upper().unique()))
    else:
        all_brands = ["All", "VIDA LOCA"]
        
    selected_brand = st.sidebar.selectbox("Filter by Brand Name", all_brands)
    
    df_actual = get_actual_inventory_cached(start_date=start_d, end_date=end_d, selected_brand=selected_brand, ignore_date=ignore_date)
    
    # 2. FILTER-WISE DIRECT QUANTITY CALCULATION FROM DATABASE
    if not df_sales.empty:
        df_sales_filtered = df_sales.copy()
        
        # Apply Date Filter if not ignored
        if not ignore_date:
            try:
                df_sales_filtered['Parsed_Date'] = pd.to_datetime(df_sales_filtered["Date"], errors='coerce').dt.date
                df_sales_filtered = df_sales_filtered[(df_sales_filtered['Parsed_Date'] >= start_d) & (df_sales_filtered['Parsed_Date'] <= end_d)]
            except: pass
            
        # Apply Brand Filter Dynamically
        if selected_brand != "All" and "BRAND" in df_sales_filtered.columns:
            df_sales_filtered = df_sales_filtered[df_sales_filtered["BRAND"].astype(str).str.upper() == selected_brand.upper()]
            
        try: total_sales_display = int(df_sales_filtered["QTY"].fillna(0).astype(int).sum())
        except: total_sales_display = 0
    else:
        total_sales_display = 0

    # 3. METRIC CARDS DISPLAY
    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1: 
        st.markdown(f'<div class="metric-container card-blue"><div class="metric-title">Total Inward Stock</div><div class="metric-value">{int(df_actual["Total Inward Stock"].sum()) if "Total Inward Stock" in df_actual.columns else 0}</div></div>', unsafe_allow_html=True)
    with m_col2: 
        st.markdown(f'<div class="metric-container card-orange"><div class="metric-title">Total Sale QTY</div><div class="metric-value">{total_sales_display}</div></div>', unsafe_allow_html=True)
    with m_col3: 
        st.markdown(f'<div class="metric-container card-green"><div class="metric-title">Actual Balance Stock</div><div class="metric-value">{int(df_actual["Actual Balance Stock"].sum()) if "Actual Balance Stock" in df_actual.columns else 0}</div></div>', unsafe_allow_html=True)
    
    st.write("---")
    df_date_summary = get_datewise_summary_cached(start_d, end_d, selected_brand=selected_brand, ignore_date=ignore_date)
    st.subheader("📅 Date-wise Stock & Sales Summary")
    if not df_date_summary.empty: st.dataframe(df_date_summary, use_container_width=True, hide_index=True)
    else: st.info("No logs found for the selected configuration.")

    st.write("---")
    st.subheader("📋 Inventory Ledger Table")
    show_cols = ["Image URL", "Product Code", "Name", "Color", "Size", "Brand", "Type", "Total Inward Stock", "Total Sold QTY", "Actual Balance Stock"]
    available_show = [c for c in show_cols if c in df_actual.columns]
    st.dataframe(df_actual[available_show], column_config={"Image URL": st.column_config.ImageColumn("Preview")}, use_container_width=True, hide_index=True)

# ==================== LIVE CHANNELS SYNC ====================
elif menu == "🔄 Live Channels Sync":
    st.markdown("<h1>🔄 Live Channel Marketplace Integrations</h1>", unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.info("🟢 Amazon SP-API: Live")
    c2.info("🟢 Flipkart API: Live")
    c3.info("🟢 Meesho API: Live")
    c4.info("🟢 Myntra API: Live")
    c5.info("🟢 Snapdeal API: Live")
    
    @st.fragment
    def sync_panel_fragment():
        st.subheader("Simulate Real-time Order Engine")
        if st.button("🔌 Run Unicommerce Sync Engine (Fetch Orders)"):
            with st.spinner("Syncing data..."):
                status_msg = simulate_live_channel_orders()
                st.success(status_msg)
        st.write("---")
        st.subheader("Current Database Sales Manifest Logs (Last 15 Rows)")
        _, _, dfs, _ = load_data_cached()
        st.dataframe(dfs.tail(15), use_container_width=True, hide_index=True)

    sync_panel_fragment()

# ==================== 1. MASTER SKU SHEET ====================
elif menu == "📦 1. MASTER SKU Sheet":
    st.markdown("<h1>📦 Master Inventory DB Records</h1>", unsafe_allow_html=True)
    
    with st.expander("🛠️ Data Management Control (Bulk / Single Entry Reset)"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🗑️ Bulk Reset")
            if st.button("🔴 Clear All Master SKU Records"):
                try:
                    supabase.table("master_sku").delete().neq("product_code", "000_BYPASS").execute()
                    clear_app_cache()
                    st.success("Master SKU ka saara data bulk me delete ho gaya hai!")
                    st.rerun()
                except Exception as e: st.error(f"Error: {e}")
        with c2:
            st.markdown("### 🔍 Single SKU Delete")
            if not df_prod.empty:
                sku_to_del = st.selectbox("Delete karne ke liye Code select karein:", df_prod["Product Code"].unique(), key="del_mst")
                if st.button("🗑️ Delete Selected SKU Record"):
                    try:
                        supabase.table("master_sku").delete().eq("product_code", sku_to_del).execute()
                        clear_app_cache()
                        st.success(f"SKU {sku_to_del} successfully delete ho gaya!")
                        st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    tab1, tab2 = st.tabs(["📁 Bulk DB Upload (Excel/CSV)", "✍️ Manual Single Entry"])
    
    with tab1:
        uploaded_file = st.file_uploader("Choose File", type=["xlsx", "csv"])
        if uploaded_file is not None:
            bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            st.dataframe(bulk_df.head(), hide_index=True)
            if st.button("🚀 Push All Records To Cloud DB"):
                try:
                    bulk_df.columns = ["category_code", "product_code", "name", "scan_identifier", "color", "size", "brand", "type", "component_product_code", "qty", "image_url"][:len(bulk_df.columns)]
                    for c in ["category_code", "product_code", "name", "scan_identifier", "color", "size", "brand", "type", "component_product_code", "image_url"]:
                        if c in bulk_df.columns: bulk_df[c] = bulk_df[c].fillna("").astype(str)
                    if "qty" in bulk_df.columns: bulk_df["qty"] = pd.to_numeric(bulk_df["qty"], errors='coerce').fillna(0).astype(int)

                    supabase.table("master_sku").delete().neq("product_code", "000").execute()
                    records = bulk_df.to_dict(orient="records")
                    supabase.table("master_sku").insert(records).execute()
                    clear_app_cache()
                    st.success("Master dataset pushed permanently to Supabase!")
                    st.rerun()
                except Exception as e: st.error(f"Database sync failed: {e}")
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
                row_data = {
                    "category_code": cat, "product_code": p_code, "name": name, "scan_identifier": p_code,
                    "color": color, "size": size, "brand": brand, "type": p_type,
                    "component_product_code": comp_code, "qty": int(qty), "image_url": img_url
                }
                try:
                    supabase.table("master_sku").insert(row_data).execute()
                    clear_app_cache()
                    st.success("New SKU committed safely to cloud database!")
                    st.rerun()
                except Exception as e: st.error(f"Error inserting row: {e}")
    st.dataframe(df_prod, use_container_width=True, hide_index=True)

# ==================== 2. CHANEL SKU MAP SHEET ====================
elif menu == "🔗 2. CHANEL SKU MAP Sheet":
    st.markdown("<h1>🔗 Channel Mapping Matrix DB</h1>", unsafe_allow_html=True)
    
    with st.expander("🛠️ Data Management Control (Bulk / Single Entry Reset)"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🗑️ Bulk Reset")
            if st.button("🔴 Clear All Connection Mappings"):
                try:
                    status_text = st.empty()
                    status_text.text("🗑️ Database ko safe chunks me saaf (wipe) kiya ja raha hai...")
                    res_ids = supabase.table("channel_sku_map").select("id").execute()
                    if res_ids.data:
                        id_list = [row["id"] for row in res_ids.data]
                        for k in range(0, len(id_list), 500):
                            chunk_ids = id_list[k:k+500]
                            supabase.table("channel_sku_map").delete().in_("id", chunk_ids).execute()
                    status_text.empty()
                    clear_app_cache()
                    st.success("Channel Mapping DB completely cleared in safe batches!")
                    st.rerun()
                except Exception as e: st.error(f"Error while wiping table: {e}")
                    
        with c2:
            st.markdown("### 🔍 Single Mapping Delete")
            if not df_map.empty:
                map_to_del = st.selectbox("Delete karne ke liye Seller SKU select karein:", df_map["Seller SKU on Channel"].unique(), key="del_map")
                if st.button("🗑️ Delete Selected Mapping Record"):
                    try:
                        supabase.table("channel_sku_map").delete().eq("seller_sku_on_channel", map_to_del).execute()
                        clear_app_cache()
                        st.success(f"Mapping for {map_to_del} successfully delete ho gayi!")
                        st.rerun()
                    except Exception as e: st.error(f"Error while deleting row: {e}")

    st.subheader("🚀 Upload New Mapping File")
    uploaded_file = st.file_uploader("Upload Connection file", type=["xlsx", "csv"])
    
    if uploaded_file is not None:
        bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        st.write("### Uploaded Data Preview:")
        st.dataframe(bulk_df.head(), hide_index=True)
        
        if st.button("🚀 Overwrite Mapping DB Table"):
            try:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_text.text("⚙️ Columns align aur clean kiye ja rahe hain...")
                bulk_df.columns = ["seller_sku_on_channel", "sku_code", "channel_name", "pack_of", "brand"][:len(bulk_df.columns)]
                
                if "seller_sku_on_channel" in bulk_df.columns: bulk_df["seller_sku_on_channel"] = bulk_df["seller_sku_on_channel"].fillna("").astype(str)
                if "sku_code" in bulk_df.columns: bulk_df["sku_code"] = bulk_df["sku_code"].fillna("").astype(str)
                if "channel_name" in bulk_df.columns: bulk_df["channel_name"] = bulk_df["channel_name"].fillna("").astype(str)
                if "brand" in bulk_df.columns: bulk_df["brand"] = bulk_df["brand"].fillna("").astype(str)
                
                if "pack_of" in bulk_df.columns:
                    bulk_df["pack_of"] = pd.to_numeric(bulk_df["pack_of"], errors='coerce').fillna(1).astype(int)
                
                status_text.text("🗑️ Clearing old records safely...")
                res_ids = supabase.table("channel_sku_map").select("id").execute()
                if res_ids.data:
                    id_list = [row["id"] for row in res_ids.data]
                    for k in range(0, len(id_list), 500):
                        supabase.table("channel_sku_map").delete().in_("id", id_list[k:k+500]).execute()
                
                records = bulk_df.to_dict(orient="records")
                total_records = len(records)
                chunk_size = 500
                
                for i in range(0, total_records, chunk_size):
                    chunk = records[i:i + chunk_size]
                    supabase.table("channel_sku_map").insert(chunk).execute()
                    percent_complete = min(100, int(((i + len(chunk)) / total_records) * 100))
                    progress_bar.progress(percent_complete)
                    status_text.text(f"⏳ Uploaded {min(i + chunk_size, total_records)} / {total_records} rows...")
                
                status_text.empty()
                progress_bar.empty()
                clear_app_cache()
                st.success("Mapping updated perfectly!")
                st.rerun()
            except Exception as e:
                st.error(f"Mapping upload failed: {e}")
                
    st.write("---")
    st.dataframe(df_map, use_container_width=True, hide_index=True)

# ==================== 3. ADD INVENTORY SHEET ====================
elif menu == "📥 3. ADD INVENTORY Sheet":
    st.markdown("<h1>📥 Stock Inward Ledger Database Panel</h1>", unsafe_allow_html=True)
    
    with st.expander("🛠️ Data Management Control (Bulk / Single Entry Reset)"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🗑️ Bulk Reset")
            if st.button("🔴 Clear All Stock Inward Logs"):
                try:
                    supabase.table("add_inventory").delete().neq("product_code", "000_BYPASS").execute()
                    clear_app_cache()
                    st.success("Inventory Stock Ledger poora bulk me delete ho gaya!")
                    st.rerun()
                except Exception as e: st.error(f"Error: {e}")
        with c2:
            st.markdown("### 🔍 Single Stock Entry Delete")
            if not df_stock.empty:
                stock_sku_del = st.selectbox("Log delete karne ke liye variant select karein:", df_stock["Product Code"].unique(), key="del_stock")
                if st.button("🗑️ Delete Selected Variant Logs"):
                    try:
                        supabase.table("add_inventory").delete().eq("product_code", stock_sku_del).execute()
                        clear_app_cache()
                        st.success(f"Stock logs for variant {stock_sku_del} successfully deleted!")
                        st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    inv_tab1, inv_tab2 = st.tabs(["📁 Bulk Inventory Upload", "✍️ Matrix Entry"])

    with inv_tab1:
        uploaded_inv_file = st.file_uploader("Choose manifest file", type=["xlsx", "csv"])
        if uploaded_inv_file is not None:
            bulk_inv_df = pd.read_csv(uploaded_inv_file) if uploaded_inv_file.name.endswith('.csv') else pd.read_excel(uploaded_inv_file)
            st.dataframe(bulk_inv_df.head(), hide_index=True)
            if st.button("🚀 Process Bulk Stock Load"):
                try:
                    bulk_inv_df.columns = ["product_code", "added_qty"][:len(bulk_inv_df.columns)]
                    bulk_inv_df["product_code"] = bulk_inv_df["product_code"].fillna("").astype(str)
                    bulk_inv_df["added_qty"] = pd.to_numeric(bulk_inv_df["added_qty"], errors='coerce').fillna(0).astype(int)
                    
                    records = bulk_inv_df.to_dict(orient="records")
                    supabase.table("add_inventory").insert(records).execute()
                    clear_app_cache()
                    st.success("Stock loaded permanently into cloud storage.")
                    st.rerun()
                except Exception as e: st.error(f"Stock upload error: {e}")

    with inv_tab2:
        unique_names = sorted(list(df_prod['Name'].dropna().unique())) if not df_prod.empty and 'Name' in df_prod.columns else []
        if unique_names:
            selected_name = st.selectbox("👗 Select Product Description", unique_names)
            filtered_by_name = df_prod[df_prod['Name'] == selected_name]
            available_colors = sorted(list(filtered_by_name['Color'].dropna().unique())) if 'Color' in filtered_by_name.columns else []
            
            if available_colors:
                selected_color = st.selectbox("🎨 Select Color", available_colors)
                final_meta = filtered_by_name[filtered_by_name['Color'] == selected_color]
                
                if not final_meta.empty and 'Product Code' in final_meta.columns:
                    base_code_sample = final_meta['Product Code'].iloc[0]
                    base_design_prefix = base_code_sample.split('-')[0] if '-' in str(base_code_sample) else base_code_sample
                    
                    size_cols = st.columns(7)
                    q_xs = size_cols[0].number_input("XS QTY", min_value=0, value=0)
                    q_s  = size_cols[1].number_input("S QTY", min_value=0, value=0)
                    q_m  = size_cols[2].number_input("M QTY", min_value=0, value=0)
                    q_l  = size_cols[3].number_input("L QTY", min_value=0, value=0)
                    q_xl = size_cols[4].number_input("XL QTY", min_value=0, value=0)
                    q_2xl = size_cols[5].number_input("XXL QTY", min_value=0, value=0)
                    q_3xl = size_cols[6].number_input("3XL QTY", min_value=0, value=0)
                    
                    if st.button("🚀 Submit Multi-Size Batch Allocation"):
                        allocations = {"XS": q_xs, "S": q_s, "M": q_m, "L": q_l, "XL": q_xl, "XXL": q_2xl, "3XL": q_3xl}
                        db_records = []
                        for sz, qty_input in allocations.items():
                            if qty_input > 0:
                                target_sku_variant = f"{base_design_prefix}-{sz}"
                                db_records.append({"product_code": target_sku_variant, "added_qty": int(qty_input)})
                        if db_records:
                            try:
                                supabase.table("add_inventory").insert(db_records).execute()
                                clear_app_cache()
                                st.success("Batch sizes submitted successfully!")
                                st.rerun()
                            except Exception as e: st.error(f"Error matrix insert: {e}")
        else: st.warning("Master SKU list is empty! Pehle data upload karein.")
                        
    st.write("---")
    st.dataframe(df_stock, use_container_width=True, hide_index=True)

# ==================== 4. SALE DATA SHEET ====================
elif menu == "📤 4. SALE DATA Sheet":
    st.markdown("<h1>📤 Channel Sales Manifest DB</h1>", unsafe_allow_html=True)
    
    with st.expander("🛠️ Data Management Control (Bulk / Single Entry Reset)"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🗑️ Bulk Reset")
            if st.button("🔴 Clear All Sales Records"):
                try:
                    supabase.table("sale_data").delete().neq("brand", "000_BYPASS").execute()
                    clear_app_cache()
                    st.success("Sales data successfully clear ho gaya!")
                    st.rerun()
                except Exception as e: st.error(f"Error: {e}")
        with c2:
            st.markdown("### 🔍 Single Order SKU Delete")
            if not df_sales.empty and "Channel SKU" in df_sales.columns:
                sku_to_del = st.selectbox("Delete karne ke liye Channel SKU select karein:", df_sales["Channel SKU"].unique(), key="del_sale")
                if st.button("🗑️ Delete Selected Sales Variant Logs"):
                    try:
                        supabase.table("sale_data").delete().eq("channel_sku", sku_to_del).execute()
                        clear_app_cache()
                        st.success(f"Sales logs for variant {sku_to_del} successfully deleted!")
                        st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    tab1, tab2 = st.tabs(["📁 Bulk Sales Upload", "✍️ Manual Entry"])

    with tab1:
        uploaded_sales_file = st.file_uploader("Choose manifest file", type=["xlsx", "csv"], key="sales_uploader")
        if uploaded_sales_file is not None:
            bulk_sales_df = pd.read_csv(uploaded_sales_file) if uploaded_sales_file.name.endswith('.csv') else pd.read_excel(uploaded_sales_file)
            st.dataframe(bulk_sales_df.head(), hide_index=True)
            if st.button("🚀 Process Bulk Sales Load"):
                try:
                    bulk_sales_df.columns = ["date", "channel_sku", "type", "brand", "qty"][:len(bulk_sales_df.columns)]
                    bulk_sales_df["channel_sku"] = bulk_sales_df["channel_sku"].fillna("").astype(str)
                    bulk_sales_df["type"] = bulk_sales_df["type"].fillna("SINGLE").astype(str)
                    bulk_sales_df["brand"] = bulk_sales_df["brand"].fillna("VIDA LOCA").astype(str)
                    bulk_sales_df["qty"] = pd.to_numeric(bulk_sales_df["qty"], errors='coerce').fillna(0).astype(int)
                    
                    records = bulk_sales_df.to_dict(orient="records")
                    supabase.table("sale_data").insert(records).execute()
                    clear_app_cache()
                    st.success("Sales data records pushed safely to database!")
                    st.rerun()
                except Exception as e: st.error(f"Sales upload error: {e}")

    with tab2:
        with st.form("manual_sales_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            s_date = col1.date_input("Order Date", date.today())
            s_sku = col2.text_input("Channel SKU (Seller SKU)").upper().strip()
            s_type = col1.selectbox("Order Item Type", ["SINGLE", "BUNDLE"])
            s_brand = col2.text_input("Brand", "VIDA LOCA")
            s_qty = col1.number_input("Sold Quantity", min_value=1, value=1)
            
            if st.form_submit_button("Log Order Entry") and s_sku:
                row_data = {
                    "date": s_date.strftime("%Y-%m-%d"), "channel_sku": s_sku,
                    "type": s_type, "brand": s_brand, "qty": int(s_qty)
                }
                try:
                    supabase.table("sale_data").insert(row_data).execute()
                    clear_app_cache()
                    st.success("Order logged permanently!")
                    st.rerun()
                except Exception as e: st.error(f"Error logging order: {e}")

    st.write("---")
    st.subheader("📋 Current Live Sales Manifest Logs")
    st.dataframe(df_sales, use_container_width=True, hide_index=True)
