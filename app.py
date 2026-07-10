import streamlit as st
import pandas as pd
from datetime import datetime, date
from supabase import create_client, Client

# --- Theme & Professional UI Configuration ---
st.set_page_config(page_title="Vida Loca Production ERP", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    h1, h2, h3 { color: #0f172a; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-weight: 700; }
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

# --- REAL SUPABASE CONNECTION ---
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Supabase Connection Error: {e}")

# --- SAFE EXCEL/CSV READER (Bypasses Openpyxl Missing Error if possible) ---
def safe_read_file(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        try:
            # First try default (which might require openpyxl)
            return pd.read_excel(uploaded_file)
        except ImportError:
            # Fallback to xlrd if old format or explicitly try forcing fallback strings
            try:
                return pd.read_excel(uploaded_file, engine='openpyxl')
            except Exception as e:
                st.error("Error: Streamlit Server par 'openpyxl' library missing hai. Kripya apne requirements.txt mein openpyxl jodein ya Excel file ko CSV format mein convert karke upload karein.")
                raise e

# --- DATA LOADING FROM LIVE DATABASE ---
def load_real_database():
    # 1. Master SKU
    try:
        res = supabase.table("master_sku").select("*").execute()
        df_p = pd.DataFrame(res.data)
        if not df_p.empty:
            cols = ["category_code", "product_code", "name", "scan_identifier", "color", "size", "brand", "type", "component_product_code", "qty", "image_url"]
            df_p = df_p[[c for c in cols if c in df_p.columns]]
            df_p.columns = ["Category Code", "Product Code", "Name", "Scan Identifier", "Color", "Size", "Brand", "Type", "Component Product Code", "QTY", "Image URL"][:len(df_p.columns)]
    except:
        df_p = pd.DataFrame()
    if df_p.empty:
        df_p = pd.DataFrame(columns=["Category Code", "Product Code", "Name", "Scan Identifier", "Color", "Size", "Brand", "Type", "Component Product Code", "QTY", "Image URL"])

    # 2. Channel SKU Map
    try:
        res = supabase.table("channel_sku_map").select("*").execute()
        df_m = pd.DataFrame(res.data)
        if not df_m.empty:
            df_m = df_m.drop(columns=["id", "created_at"], errors="ignore")
            df_m.columns = ["Seller SKU on Channel", "SKU Code", "Channel Name", "Pack Of", "Brand"][:len(df_m.columns)]
    except:
        df_m = pd.DataFrame()
    if df_m.empty:
        df_m = pd.DataFrame(columns=["Seller SKU on Channel", "SKU Code", "Channel Name", "Pack Of", "Brand"])

    # 3. Real Sales Data
    try:
        res = supabase.table("sale_data").select("*").execute()
        df_sa = pd.DataFrame(res.data)
        if not df_sa.empty:
            df_sa = df_sa.drop(columns=["id", "created_at"], errors="ignore")
            df_sa.columns = ["Date", "Channel SKU", "Type", "Brand", "QTY"][:len(df_sa.columns)]
    except:
        df_sa = pd.DataFrame()
    if df_sa.empty:
        df_sa = pd.DataFrame(columns=["Date", "Channel SKU", "Type", "Brand", "QTY"])

    # 4. Inward Stock Data
    try:
        res = supabase.table("add_inventory").select("*").execute()
        df_st = pd.DataFrame(res.data)
        if not df_st.empty:
            df_st = df_st.drop(columns=["id", "created_at"], errors="ignore")
            df_st.columns = ["Date & Time", "Product Code", "Added QTY"][:len(df_st.columns)]
    except:
        df_st = pd.DataFrame()
    if df_st.empty:
        df_st = pd.DataFrame(columns=["Date & Time", "Product Code", "Added QTY"])

    return df_p, df_m, df_sa, df_st

def clear_cache():
    st.cache_data.clear()

def clean_sku(val):
    if pd.isna(val): return ""
    s = str(val).strip().upper()
    if s.endswith('.0'): s = s[:-2]
    return s

# --- REAL INVENTORY LEDGER ENGINE ---
def calculate_real_inventory(start_date=None, end_date=None, selected_brand="All", ignore_date=True):
    df_p, df_m, df_sa, df_st = load_real_database()
    
    if selected_brand != "All" and "Brand" in df_p.columns:
        df_p = df_p[df_p["Brand"] == selected_brand]
        
    inward_stock = {}
    for _, r in df_p.iterrows():
        code = clean_sku(r["Product Code"])
        try: inward_stock[code] = int(r["QTY"]) if pd.notna(r["QTY"]) else 0
        except: inward_stock[code] = 0
                
    sold_stock = {code: 0 for code in inward_stock.keys()}
    
    # Process Real Inward Inventory
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

    # Process Real Sales Data
    if not df_sa.empty and not ignore_date:
        try:
            df_sa['Parsed_Date'] = pd.to_datetime(df_sa["Date"], errors='coerce').dt.date
            if start_date and end_date:
                df_sa = df_sa[(df_sa['Parsed_Date'] >= start_date) & (df_sa['Parsed_Date'] <= end_date)]
        except: pass

    chanel_map = {}
    if not df_m.empty:
        for _, m_row in df_m.iterrows():
            c_sku = clean_sku(m_row["Seller SKU on Channel"])
            s_code = clean_sku(m_row["SKU Code"])
            if c_sku: chanel_map[c_sku] = s_code

    if not df_sa.empty:
        for _, sale in df_sa.iterrows():
            sku_input = clean_sku(sale["Channel SKU"])
            try: s_qty = int(sale["QTY"]) if pd.notna(sale["QTY"]) else 0
            except: s_qty = 0
            
            sale_type = str(sale["Type"]).strip().upper() if pd.notna(sale["Type"]) else "SINGLE"
            if not sku_input: continue

            if sale_type in ["BUNDAL", "BUNDLE"]:
                matches = df_p[df_p["Scan Identifier"].astype(str).str.strip().str.upper() == sku_input]
                match_count = 0
                for _, m_row in matches.iterrows():
                    comp_sku = clean_sku(m_row["Component Product Code"])
                    if comp_sku in sold_stock: sold_stock[comp_sku] += s_qty
                    match_count += 1
                    if match_count == 2: break
            else:
                found_sku = chanel_map.get(sku_input, sku_input)
                if found_sku in sold_stock:
                    sold_stock[found_sku] += s_qty
                else:
                    comp_matches = df_p[df_p["Component Product Code"].astype(str).str.strip().str.upper() == found_sku]
                    for _, c_row in comp_matches.iterrows():
                        c_code = clean_sku(c_row["Product Code"])
                        if c_code in sold_stock: sold_stock[c_code] += s_qty
                    if sku_input in sold_stock:
                        sold_stock[sku_input] += s_qty

    total_inward_list, total_sold_list, balance_list = [], [], []
    for _, row in df_p.iterrows():
        code = clean_sku(row["Product Code"])
        total_in = inward_stock.get(code, 0)
        total_sold = sold_stock.get(code, 0)
        total_inward_list.append(total_in)
        total_sold_list.append(total_sold)
        balance_list.append(total_in - total_sold)
        
    df_p['Total Inward Stock'] = total_inward_list
    df_p['Total Sold QTY'] = total_sold_list
    df_p['Actual Balance Stock'] = balance_list
    return df_p

# ---- Sidebar Production Navigation ----
st.sidebar.markdown("<h2 style='color:white; text-align:center;'>Vida Loca ERP Pro</h2>", unsafe_allow_html=True)
st.sidebar.write("---")
menu = st.sidebar.radio("Navigation Panel:", [
    "📊 Live Business Dashboard", 
    "📦 Master SKU Management", 
    "🔗 Channel SKU Mapping", 
    "📥 Inward Stock Inventory", 
    "📤 Sales Order Upload"
])

df_prod, df_map, df_sales, df_stock = load_real_database()

# ==================== LIVE BUSINESS DASHBOARD ====================
if menu == "📊 Live Business Dashboard":
    st.markdown("<h1>📊 Live Business Operations Dashboard</h1>", unsafe_allow_html=True)
    
    today = date.today()
    start_d = st.sidebar.date_input("Filter Start Date", date(today.year, 1, 1))
    end_d = st.sidebar.date_input("Filter End Date", today)
    ignore_date = st.sidebar.checkbox("Show All-Time Lifetime Records", value=True)
    
    all_brands = ["All"] + list(df_prod['Brand'].dropna().unique()) if not df_prod.empty and 'Brand' in df_prod.columns else ["All"]
    selected_brand = st.sidebar.selectbox("Filter by Brand", all_brands)
    
    df_actual = calculate_real_inventory(start_date=start_d, end_date=end_d, selected_brand=selected_brand, ignore_date=ignore_date)
        
    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1: st.markdown(f'<div class="metric-container card-blue"><div class="metric-title">Total Operational Stock (Inward)</div><div class="metric-value">{int(df_actual["Total Inward Stock"].sum()) if "Total Inward Stock" in df_actual.columns else 0} Pcs</div></div>', unsafe_allow_html=True)
    with m_col2: st.markdown(f'<div class="metric-container card-orange"><div class="metric-title">Total Orders Dispatched (Sales)</div><div class="metric-value">{int(df_actual["Total Sold QTY"].sum()) if "Total Sold QTY" in df_actual.columns else 0} Pcs</div></div>', unsafe_allow_html=True)
    with m_col3: st.markdown(f'<div class="metric-container card-green"><div class="metric-title">Current Net Warehouse Balance</div><div class="metric-value">{int(df_actual["Actual Balance Stock"].sum()) if "Actual Balance Stock" in df_actual.columns else 0} Pcs</div></div>', unsafe_allow_html=True)
    
    st.write("---")
    st.subheader("📋 Real-Time Inventory Ledger Table")
    show_cols = ["Image URL", "Product Code", "Name", "Color", "Size", "Brand", "Type", "Total Inward Stock", "Total Sold QTY", "Actual Balance Stock"]
    available_show = [c for c in show_cols if c in df_actual.columns]
    st.dataframe(df_actual[available_show], column_config={"Image URL": st.column_config.ImageColumn("Preview")}, use_container_width=True, hide_index=True)

# ==================== MASTER SKU MANAGEMENT ====================
elif menu == "📦 Master SKU Management":
    st.markdown("<h1>📦 Master Inventory Database Management</h1>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Upload Master SKU File (Excel/CSV)", type=["xlsx", "csv"])
    if uploaded_file is not None:
        bulk_df = safe_read_file(uploaded_file)
        st.write("File Preview:")
        st.dataframe(bulk_df.head(), hide_index=True)
        
        if st.button("🚀 Push Verified Dataset to Production Cloud"):
            try:
                bulk_df.columns = ["category_code", "product_code", "name", "scan_identifier", "color", "size", "brand", "type", "component_product_code", "qty", "image_url"][:len(bulk_df.columns)]
                for c in bulk_df.columns:
                    if c != "qty": bulk_df[c] = bulk_df[c].fillna("").astype(str)
                if "qty" in bulk_df.columns:
                    bulk_df["qty"] = pd.to_numeric(bulk_df["qty"], errors='coerce').fillna(0).astype(int)

                # Clear old production table safely
                supabase.table("master_sku").delete().neq("product_code", "000_SAFE_KEEP").execute()
                records = bulk_df.to_dict(orient="records")
                supabase.table("master_sku").insert(records).execute()
                clear_cache()
                st.success("Production Database Synchronized Successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Sync Failed: {e}")
                
    st.write("---")
    st.subheader("Current Live Master Database Items")
    st.dataframe(df_prod, use_container_width=True, hide_index=True)

# ==================== CHANNEL SKU MAPPING ====================
elif menu == "🔗 Channel SKU Mapping":
    st.markdown("<h1>🔗 Channel Mapping Matrix (Amazon/Flipkart/Meesho/Myntra/Snapdeal)</h1>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Upload Channel Sync Mapping File", type=["xlsx", "csv"])
    if uploaded_file is not None:
        bulk_df = safe_read_file(uploaded_file)
        st.dataframe(bulk_df.head(), hide_index=True)
        
        if st.button("🚀 Overwrite & Update Live Production Mapping"):
            try:
                bulk_df.columns = ["seller_sku_on_channel", "sku_code", "channel_name", "pack_of", "brand"][:len(bulk_df.columns)]
                for c in bulk_df.columns:
                    bulk_df[c] = bulk_df[c].fillna("")
                
                supabase.table("channel_sku_map").delete().neq("sku_code", "000_SAFE_KEEP").execute()
                records = bulk_df.to_dict(orient="records")
                supabase.table("channel_sku_map").insert(records).execute()
                clear_cache()
                st.success("Marketplace Mappings Live Now!")
                st.rerun()
            except Exception as e:
                st.error(f"Mapping upload failed: {e}")
                
    st.write("---")
    st.subheader("Active Marketplace Mapping Index")
    st.dataframe(df_map, use_container_width=True, hide_index=True)

# ==================== INWARD STOCK INVENTORY ====================
elif menu == "📥 Inward Stock Inventory":
    st.markdown("<h1>📥 Warehouse Inward Stock Ledger</h1>", unsafe_allow_html=True)
    
    uploaded_inv_file = st.file_uploader("Upload Fresh Stock Inward Manifest", type=["xlsx", "csv"])
    if uploaded_inv_file is not None:
        bulk_inv_df = safe_read_file(uploaded_inv_file)
        st.dataframe(bulk_inv_df.head(), hide_index=True)
        
        if st.button("🚀 Log Stock into Production Warehouse"):
            try:
                bulk_inv_df.columns = ["product_code", "added_qty"][:len(bulk_inv_df.columns)]
                bulk_inv_df["product_code"] = bulk_inv_df["product_code"].fillna("").astype(str)
                bulk_inv_df["added_qty"] = pd.to_numeric(bulk_inv_df["added_qty"], errors='coerce').fillna(0).astype(int)
                
                records = bulk_inv_df.to_dict(orient="records")
                supabase.table("add_inventory").insert(records).execute()
                clear_cache()
                st.success("Stock logged permanently into secure live cloud storage.")
                st.rerun()
            except Exception as e:
                st.error(f"Stock ledger sync failed: {e}")
                
    st.write("---")
    st.subheader("Inward Audit Trails (Logs)")
    st.dataframe(df_stock, use_container_width=True, hide_index=True)

# ==================== SALES ORDER UPLOAD ====================
elif menu == "📤 Sales Order Upload":
    st.markdown("<h1>📤 Portal Dispatch Orders Sync Manifest</h1>", unsafe_allow_html=True)
    st.info("Yahan aap Amazon, Meesho, Myntra, Flipkart ya Snapdeal ka sales data manifest direct push kar sakte hain.")
    
    uploaded_file = st.file_uploader("Upload Marketplace Sales Manifest", type=["xlsx", "csv"])
    if uploaded_file is not None:
        bulk_df = safe_read_file(uploaded_file)
        st.dataframe(bulk_df.head(), hide_index=True)
        
        if st.button("🚀 Push Orders To Production Engine"):
            try:
                bulk_df.columns = ["date", "channel_sku", "type", "brand", "qty"][:len(bulk_df.columns)]
                bulk_df['date'] = pd.to_datetime(bulk_df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
                bulk_df['date'] = bulk_df['date'].fillna(datetime.now().strftime('%Y-%m-%d'))
                
                bulk_df["channel_sku"] = bulk_df["channel_sku"].fillna("").astype(str)
                bulk_df["type"] = bulk_df["type"].fillna("SINGLE").astype(str)
                bulk_df["brand"] = bulk_df["brand"].fillna("VIDA LOCA").astype(str)
                bulk_df["qty"] = pd.to_numeric(bulk_df["qty"], errors='coerce').fillna(0).astype(int)

                records = bulk_df.to_dict(orient="records")
                supabase.table("sale_data").insert(records).execute()
                clear_cache()
                st.success("Sales orders processed and ledger balances auto-updated!")
                st.rerun()
            except Exception as e:
                st.error(f"Sales engine failed to update: {e}")
                
    st.write("---")
    st.subheader("Processed Market Orders Database Registry")
    st.dataframe(df_sales, use_container_width=True, hide_index=True)
