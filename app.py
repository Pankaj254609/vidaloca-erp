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
        limit = 4000  
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

# --- ULTRA FAST INVENTORY ENGINE ---
def get_actual_inventory_cached(start_date=None, end_date=None, selected_brand="All", ignore_date=False):
    df_p, df_m, df_sa, df_st = load_data_cached()
    
    df_p["Product Code Clean"] = df_p["Product Code"].apply(clean_sku)
    df_p["QTY"] = pd.to_numeric(df_p["QTY"], errors='coerce').fillna(0).astype(int)
    
    # 1. Process Inward
    inward_map = {}
    if not df_st.empty:
        df_st_cp = df_st.copy()
        df_st_cp["Product Code Clean"] = df_st_cp["Product Code"].apply(clean_sku)
        df_st_cp["Added QTY"] = pd.to_numeric(df_st_cp["Added QTY"], errors='coerce').fillna(0).astype(int)
        
        if not ignore_date and start_date and end_date:
            try:
                df_st_cp['Parsed_Date'] = pd.to_datetime(df_st_cp["Date & Time"], errors='coerce').dt.date
                df_st_cp = df_st_cp[(df_st_cp['Parsed_Date'] >= start_date) & (df_st_cp['Parsed_Date'] <= end_date)]
            except: pass
            
        inward_map = df_st_cp.groupby("Product Code Clean")["Added QTY"].sum().to_dict()
        
    df_p["Inward Log Added"] = df_p["Product Code Clean"].map(inward_map).fillna(0).astype(int)
    df_p["Total Inward Stock"] = df_p["QTY"] + df_p["Inward Log Added"]

    # 2. Process Sales
    sold_stock = {code: 0 for code in df_p["Product Code Clean"].unique()}
    
    if not df_sa.empty:
        df_sa_cp = df_sa.copy()
        df_sa_cp["Channel SKU Clean"] = df_sa_cp["Channel SKU"].apply(clean_sku)
        df_sa_cp["Qty"] = pd.to_numeric(df_sa_cp["Qty"], errors='coerce').fillna(0).astype(int)
        
        if not ignore_date and start_date and end_date:
            try:
                df_sa_cp['Parsed_Date'] = pd.to_datetime(df_sa_cp["Date"], errors='coerce').dt.date
                df_sa_cp = df_sa_cp[(df_sa_cp['Parsed_Date'] >= start_date) & (df_sa_cp['Parsed_Date'] <= end_date)]
            except: pass
            
        if selected_brand != "All" and "Brand" in df_sa_cp.columns:
            df_sa_cp = df_sa_cp[df_sa_cp["Brand"].astype(str).str.strip().str.upper() == selected_brand.upper()]
            
        chanel_map = {}
        if not df_m.empty:
            chanel_map = dict(zip(df_m["Seller SKU on Channel"].apply(clean_sku), df_m["SKU Code"].apply(clean_sku)))
            
        df_sa_cp["Mapped SKU"] = df_sa_cp["Channel SKU Clean"].map(chanel_map).fillna(df_sa_cp["Channel SKU Clean"])
        
        sales_summary = df_sa_cp.groupby(["Mapped SKU", "Type"])["Qty"].sum().to_dict()
        
        scan_to_comp = dict(zip(df_p["Scan Identifier"].apply(clean_sku), df_p["Component Product Code"].apply(clean_sku)))
        comp_to_prod = dict(zip(df_p["Component Product Code"].apply(clean_sku), df_p["Product Code Clean"]))
        
        for (sku, s_type), qty in sales_summary.items():
            if s_type in ["BUNDAL", "BUNDLE"]:
                comp_sku = scan_to_comp.get(sku, "")
                if comp_sku in sold_stock: sold_stock[comp_sku] += qty
            else:
                if sku in sold_stock:
                    sold_stock[sku] += qty
                else:
                    alt_sku = comp_to_prod.get(sku, "")
                    if alt_sku in sold_stock:
                        sold_stock[alt_sku] += qty
                    elif sku in sold_stock:
                        sold_stock[sku] += qty

    df_p["Total Sold QTY"] = df_p["Product Code Clean"].map(sold_stock).fillna(0).astype(int)
    df_p["Actual Balance Stock"] = df_p["Total Inward Stock"] - df_p["Total Sold QTY"]
    
    if selected_brand != "All" and "Brand" in df_p.columns:
        df_p = df_p[df_p["Brand"].astype(str).str.strip().str.upper() == selected_brand.upper()]
        
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
            inward_by_date = df_filtered_st.groupby("Date_Only")["Added QTY"].sum().to_dict()
        except: pass

    sales_by_date = {}
    if not df_sa.empty:
        try:
            df_sa['Date_Only'] = pd.to_datetime(df_sa["Date"], errors='coerce').dt.date
            df_filtered_sa = df_sa[df_sa['Date_Only'].notna()]
            if not ignore_date:
                df_filtered_sa = df_filtered_sa[(df_filtered_sa['Date_Only'] >= start_date) & (df_filtered_sa['Date_Only'] <= end_date)]
            if selected_brand != "All" and "Brand" in df_filtered_sa.columns:
                df_filtered_sa = df_filtered_sa[df_filtered_sa["Brand"].astype(str).str.strip().str.upper() == selected_brand.upper()]
            
            df_filtered_sa["Qty"] = pd.to_numeric(df_filtered_sa["Qty"], errors='coerce').fillna(0).astype(int)
            sales_by_date = df_filtered_sa.groupby("Date_Only")["Qty"].sum().to_dict()
        except: pass

    all_dates = sorted(list(set(list(inward_by_date.keys()) + list(sales_by_date.keys()))))
    summary_records = []
    for d in all_dates:
        summary_records.append({
            "Date": d.strftime("%Y-%m-%d"),
            "Total Inward QTY": int(inward_by_date.get(d, 0)),
            "Total Sales QTY": int(sales_by_date.get(d, 0))
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
    
    # Clean unique brand list extraction to prevent duplicates
    all_brands = ["All"]
    if not df_sales.empty and "Brand" in df_sales.columns:
        all_brands += sorted(list(df_sales['Brand'].dropna().astype(str).str.strip().str.upper().unique()))
    elif not df_prod.empty and 'Brand' in df_prod.columns:
        all_brands += sorted(list(df_prod['Brand'].dropna().astype(str).str.strip().str.upper().unique()))
    else:
        all_brands += ["VIDA LOCA", "YUGNIK"]
    
    # Remove any duplicates if exist
    all_brands = sorted(list(set(all_brands)), key=lambda x: (x != "All", x))
        
    selected_brand = st.sidebar.selectbox("Filter by Brand Name", all_brands)
    
    # 1. Fetch accurate mapped matrix ledger table
    df_actual = get_actual_inventory_cached(start_date=start_d, end_date=end_d, selected_brand=selected_brand, ignore_date=ignore_date)
    
    # 2. Strict Filter Metric Calculation for Orange Card
    if not df_sales.empty:
        df_sales_filtered = df_sales.copy()
        df_sales_filtered["Qty"] = pd.to_numeric(df_sales_filtered["Qty"], errors='coerce').fillna(0).astype(int)
            
        if not ignore_date:
            try:
                df_sales_filtered['Parsed_Date'] = pd.to_datetime(df_sales_filtered["Date"], errors='coerce').dt.date
                df_sales_filtered = df_sales_filtered[(df_sales_filtered['Parsed_Date'] >= start_d) & (df_sales_filtered['Parsed_Date'] <= end_d)]
            except: pass
            
        if selected_brand != "All" and "Brand" in df_sales_filtered.columns:
            df_sales_filtered = df_sales_filtered[df_sales_filtered["Brand"].astype(str).str.strip().str.upper() == selected_brand.upper()]
            
        total_sales_display = int(df_sales_filtered["Qty"].sum())
    else:
        total_sales_display = 0

    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1: 
        st.markdown(f'<div class="metric-container card-blue"><div class="metric-title">Total Inward Stock</div><div class="metric-value">{int(df_actual["Total Inward Stock"].sum()) if "Total Inward Stock" in df_actual.columns else 0}</div></div>', unsafe_allow_html=True)
    with m_col2: 
        # Display the real un-truncated sum metric
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

# ==================== CONTROLS FOR PAGES (REST REMAIN SECURE) ====================
elif menu == "🔄 Live Channels Sync":
    st.markdown("<h1>🔄 Live Channel Marketplace Integrations</h1>", unsafe_allow_html=True)
    st.subheader("Current Database Sales Manifest Logs (Last 15 Rows)")
    st.dataframe(df_sales.tail(15), use_container_width=True, hide_index=True)

elif menu == "📦 1. MASTER SKU Sheet":
    st.markdown("<h1>📦 Master Inventory DB Records</h1>", unsafe_allow_html=True)
    st.dataframe(df_prod, use_container_width=True, hide_index=True)

elif menu == "🔗 2. CHANEL SKU MAP Sheet":
    st.markdown("<h1>🔗 Channel Mapping Matrix DB</h1>", unsafe_allow_html=True)
    st.dataframe(df_map, use_container_width=True, hide_index=True)

elif menu == "📥 3. ADD INVENTORY Sheet":
    st.markdown("<h1>📥 Stock Inward Ledger Database Panel</h1>", unsafe_allow_html=True)
    st.dataframe(df_stock, use_container_width=True, hide_index=True)

elif menu == "📤 4. SALE DATA Sheet":
    st.markdown("<h1>📤 Channel Sales Manifest DB</h1>", unsafe_allow_html=True)
    st.dataframe(df_sales, use_container_width=True, hide_index=True)
