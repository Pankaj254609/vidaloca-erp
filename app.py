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

# --- SUPER FAST DATA FETCH WITH OPTIMIZED CHUNKING & CACHING ---
@st.cache_data(ttl=600, show_spinner="⚡ Cloud Database se Data Fast Fetch ho raha hai...")
def load_data_cached():
    def fetch_all_rows_fast(table_name):
        all_data = []
        start = 0
        limit = 4000  # Efficient big chunk to reduce network API roundtrips
        
        while True:
            try:
                res = supabase.table(table_name).select("*").range(start, start + limit - 1).execute()
                if not res.data or len(res.data) == 0:
                    break
                all_data.extend(res.data)
                if len(res.data) < limit:
                    break
                start += limit
            except Exception as e:
                st.error(f"Error fetching from {table_name}: {e}")
                break
        return pd.DataFrame(all_data)

    # 1. Master SKU Fetch
    try:
        df_p = fetch_all_rows_fast("master_sku")
        if not df_p.empty:
            actual_cols = ["category_code", "product_code", "name", "scan_identifier", "color", "size", "brand", "type", "component_product_code", "qty", "image_url"]
            df_p = df_p[[c for c in actual_cols if c in df_p.columns]]
            df_p.columns = ["Category Code", "Product Code", "Name", "Scan Identifier", "Color", "Size", "Brand", "Type", "Component Product Code", "QTY", "Image URL"][:len(df_p.columns)]
    except:
        df_p = pd.DataFrame()
    if df_p.empty:
        df_p = pd.DataFrame(columns=["Category Code", "Product Code", "Name", "Scan Identifier", "Color", "Size", "Brand", "Type", "Component Product Code", "QTY", "Image URL"])

    # 2. Mapping Matrix Fetch
    try:
        df_m = fetch_all_rows_fast("channel_sku_map")
        if not df_m.empty:
            df_m = df_m.drop(columns=["id", "created_at"], errors="ignore")
            df_m.columns = ["Seller SKU on Channel", "SKU Code", "channelName", "PACK OF", "BRAND"][:len(df_m.columns)]
    except:
        df_m = pd.DataFrame()
    if df_m.empty:
        df_m = pd.DataFrame(columns=["Seller SKU on Channel", "SKU Code", "channelName", "PACK OF", "BRAND"])

    # 3. Sales Fetch with String Header Uniformity
    try:
        df_sa = fetch_all_rows_fast("sale_data")
        if not df_sa.empty:
            df_sa = df_sa.drop(columns=["id", "created_at"], errors="ignore")
            df_sa.columns = [str(c).strip().upper() for c in df_sa.columns]
            
            rename_dict = {}
            for col in df_sa.columns:
                if col in ["DATE"]: rename_dict[col] = "Date"
                elif col in ["CHANNEL_SKU", "ITEM SKU CODE", "ITEM_SKU_CODE", "SKU"]: rename_dict[col] = "Channel SKU"
                elif col in ["TYPE"]: rename_dict[col] = "Type"
                elif col in ["BRAND"]: rename_dict[col] = "Brand"
                elif col in ["QTY", "QUANTITY"]: rename_dict[col] = "Qty"
            df_sa = df_sa.rename(columns=rename_dict)
    except:
        df_sa = pd.DataFrame()
    if df_sa.empty:
        df_sa = pd.DataFrame(columns=["Date", "Channel SKU", "Type", "Brand", "Qty"])

    # 4. Stock Fetch
    try:
        df_st = fetch_all_rows_fast("add_inventory")
        if not df_st.empty:
            df_st = df_st.drop(columns=["id", "created_at"], errors="ignore")
            df_st.columns = ["Date & Time", "Product Code", "Added QTY"][:len(df_st.columns)]
    except:
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

def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

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
            if selected_brand != "All" and "Brand" in df_sa.columns:
                df_sa = df_sa[df_sa["Brand"].astype(str).str.upper() == selected_brand.upper()]
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
            sku_input = clean_sku(sale.get("Channel SKU", ""))
            try: s_qty = int(sale.get("Qty", 0)) if pd.notna(sale.get("Qty", 0)) else 0
            except: s_qty = 0
            
            sale_type = str(sale.get("Type", "SINGLE")).strip().upper()

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
            
            if selected_brand != "All" and "Brand" in df_filtered_sa.columns:
                df_filtered_sa = df_filtered_sa[df_filtered_sa["Brand"].astype(str).str.upper() == selected_brand.upper()]
            
            for _, sale in df_filtered_sa.iterrows():
                try: s_qty = int(sale["Qty"]) if pd.notna(sale["Qty"]) else 0
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
    
    if not df_sales.empty and "Brand" in df_sales.columns:
        all_brands = ["All"] + sorted(list(df_sales['Brand'].dropna().astype(str).str.upper().unique()))
    elif not df_prod.empty and 'Brand' in df_prod.columns:
        all_brands = ["All"] + sorted(list(df_prod['Brand'].dropna().astype(str).str.upper().unique()))
    else:
        all_brands = ["All", "VIDA LOCA"]
        
    selected_brand = st.sidebar.selectbox("Filter by Brand Name", all_brands)
    
    df_actual = get_actual_inventory_cached(start_date=start_d, end_date=end_d, selected_brand=selected_brand, ignore_date=ignore_date)
    
    if not df_sales.empty:
        df_sales_filtered = df_sales.copy()
        if not ignore_date:
            try:
                df_sales_filtered['Parsed_Date'] = pd.to_datetime(df_sales_filtered["Date"], errors='coerce').dt.date
                df_sales_filtered = df_sales_filtered[(df_sales_filtered['Parsed_Date'] >= start_d) & (df_sales_filtered['Parsed_Date'] <= end_d)]
            except: pass
            
        if selected_brand != "All" and "Brand" in df_sales_filtered.columns:
            df_sales_filtered = df_sales_filtered[df_sales_filtered["Brand"].astype(str).str.upper() == selected_brand.upper()]
            
        try: total_sales_display = int(df_sales_filtered["Qty"].fillna(0).astype(int).sum())
        except: total_sales_display = 0
    else:
        total_sales_display = 0

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
    
    st.subheader("Current Database Sales Manifest Logs (Last 15 Rows)")
    st.dataframe(df_sales.tail(15), use_container_width=True, hide_index=True)

# ==================== 1. MASTER SKU SHEET ====================
elif menu == "📦 1. MASTER SKU Sheet":
    st.markdown("<h1>📦 Master Inventory DB Records</h1>", unsafe_allow_html=True)
    
    if not df_prod.empty:
        st.download_button(
            label="📥 Download Complete Master SKU Sheet (CSV)",
            data=convert_df_to_csv(df_prod),
            file_name=f"Master_SKU_Full_{date.today()}.csv",
            mime="text/csv",
            key="download_master_full"
        )
        st.caption(f"📊 Total Records Found in Database: {len(df_prod)} rows")

    tab1, tab2 = st.tabs(["📁 Bulk DB Upload (Excel/CSV)", "✍️ Manual Single Entry"])
    with tab1:
        uploaded_file = st.file_uploader("Choose File", type=["xlsx", "csv"])
        if uploaded_file is not None:
            bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            if st.button("🚀 Push All Records To Cloud DB"):
                try:
                    bulk_df.columns = ["category_code", "product_code", "name", "scan_identifier", "color", "size", "brand", "type", "component_product_code", "qty", "image_url"][:len(bulk_df.columns)]
                    for c in bulk_df.columns: bulk_df[c] = bulk_df[c].fillna("").astype(str)
                    records = bulk_df.to_dict(orient="records")
                    supabase.table("master_sku").delete().neq("product_code", "000").execute()
                    supabase.table("master_sku").insert(records).execute()
                    clear_app_cache()
                    st.success("Master SKU Uploaded!")
                    st.rerun()
                except Exception as e: st.error(f"Error: {e}")
                
    st.dataframe(df_prod, use_container_width=True, hide_index=True)

# ==================== 2. CHANEL SKU MAP SHEET ====================
elif menu == "🔗 2. CHANEL SKU MAP Sheet":
    st.markdown("<h1>🔗 Channel Mapping Matrix DB</h1>", unsafe_allow_html=True)
    
    if not df_map.empty:
        st.download_button(
            label="📥 Download Complete Channel SKU Map (CSV)",
            data=convert_df_to_csv(df_map),
            file_name=f"Channel_SKU_Map_Full_{date.today()}.csv",
            mime="text/csv",
            key="download_map_full"
        )
        st.caption(f"📊 Total Records Found in Database: {len(df_map)} rows")

    uploaded_file = st.file_uploader("Upload Connection file", type=["xlsx", "csv"])
    if uploaded_file is not None:
        bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        if st.button("🚀 Overwrite Mapping DB Table"):
            try:
                bulk_df.columns = ["seller_sku_on_channel", "sku_code", "channel_name", "pack_of", "brand"][:len(bulk_df.columns)]
                records = bulk_df.to_dict(orient="records")
                supabase.table("channel_sku_map").delete().neq("sku_code", "000").execute()
                for i in range(0, len(records), 500):
                    supabase.table("channel_sku_map").insert(records[i:i+500]).execute()
                clear_app_cache()
                st.success("Mapping Matrix Updated!")
                st.rerun()
            except Exception as e: st.error(f"Error: {e}")
            
    st.dataframe(df_map, use_container_width=True, hide_index=True)

# ==================== 3. ADD INVENTORY SHEET ====================
elif menu == "📥 3. ADD INVENTORY Sheet":
    st.markdown("<h1>📥 Stock Inward Ledger Database Panel</h1>", unsafe_allow_html=True)
    
    if not df_stock.empty:
        st.download_button(
            label="📥 Download Complete Stock Inward Ledger (CSV)",
            data=convert_df_to_csv(df_stock),
            file_name=f"Stock_Inward_Full_{date.today()}.csv",
            mime="text/csv",
            key="download_stock_full"
        )
        st.caption(f"📊 Total Records Found in Database: {len(df_stock)} rows")

    uploaded_inv_file = st.file_uploader("Choose manifest file", type=["xlsx", "csv"])
    if uploaded_inv_file is not None:
        bulk_inv_df = pd.read_csv(uploaded_inv_file) if uploaded_inv_file.name.endswith('.csv') else pd.read_excel(uploaded_inv_file)
        if st.button("🚀 Process Bulk Stock Load"):
            try:
                bulk_inv_df.columns = ["product_code", "added_qty"][:len(bulk_inv_df.columns)]
                records = bulk_inv_df.to_dict(orient="records")
                supabase.table("add_inventory").insert(records).execute()
                clear_app_cache()
                st.success("Inventory Logs Added!")
                st.rerun()
            except Exception as e: st.error(f"Error: {e}")
            
    st.dataframe(df_stock, use_container_width=True, hide_index=True)

# ==================== 4. SALE DATA SHEET ====================
elif menu == "📤 4. SALE DATA Sheet":
    st.markdown("<h1>📤 Channel Sales Manifest DB</h1>", unsafe_allow_html=True)
    
    if not df_sales.empty:
        st.download_button(
            label="📥 Download Complete Sale Data Manifest (CSV)",
            data=convert_df_to_csv(df_sales),
            file_name=f"Sale_Data_Full_{date.today()}.csv",
            mime="text/csv",
            key="download_sales_full"
        )
        st.caption(f"📊 Total Records Found in Database: {len(df_sales)} rows")

    uploaded_sales_file = st.file_uploader("Choose manifest file", type=["xlsx", "csv"])
    if uploaded_sales_file is not None:
        bulk_sales_df = pd.read_csv(uploaded_sales_file) if uploaded_sales_file.name.endswith('.csv') else pd.read_excel(uploaded_sales_file)
        if st.button("🚀 Process Bulk Sales Load"):
            try:
                bulk_sales_df.columns = ["date", "channel_sku", "type", "brand", "qty"][:len(bulk_sales_df.columns)]
                records = bulk_sales_df.to_dict(orient="records")
                supabase.table("sale_data").insert(records).execute()
                clear_app_cache()
                st.success("Sales Data Injected Successfully!")
                st.rerun()
            except Exception as e: st.error(f"Error: {e}")
            
    st.dataframe(df_sales, use_container_width=True, hide_index=True)
