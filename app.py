import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- Theme Configuration ---
st.set_page_config(page_title="Vida Loca Advanced ERP", layout="wide")

# Custom CSS for OMS Guru Style Premium Interface
st.markdown("""
    <style>
    /* Main Background & Fonts */
    .main { background-color: #f8f9fa; }
    h1, h2, h3 { color: #1e293b; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-weight: 700; }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #0f172a !important;
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] *.stText, [data-testid="stSidebar"] label, [data-testid="stSidebar"] h1 {
        color: #ffffff !important;
    }
    
    /* Custom Metric Cards Style like OMS Guru */
    .metric-container {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
        border-left: 6px solid #3b82f6;
        margin-bottom: 15px;
    }
    .metric-title { font-size: 14px; color: #64748b; font-weight: 600; text-transform: uppercase; }
    .metric-value { font-size: 28px; color: #1e293b; font-weight: 700; margin-top: 5px; }
    
    /* Color Highlights for different metrics */
    .card-blue { border-left-color: #3b82f6; }
    .card-orange { border-left-color: #f97316; }
    .card-green { border-left-color: #10b981; }
    
    /* Forms and Tabs styling */
    .stButton>button {
        background-color: #3b82f6 !important;
        color: white !important;
        border-radius: 8px !important;
        padding: 8px 24px !important;
        font-weight: 600 !important;
        border: none !important;
        box-shadow: 0 4px 6px rgba(59, 130, 246, 0.2);
    }
    .stButton>button:hover {
        background-color: #2563eb !important;
        transform: translateY(-1px);
    }
    .stTabs [data-baseweb="tab"] {
        font-weight: 600;
        color: #64748b;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #3b82f6 !important;
        border-bottom-color: #3b82f6 !important;
    }
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

    return pd.read_csv(PROD_FILE), pd.read_csv(MAP_FILE), pd.read_csv(SALES_FILE), pd.read_csv(STOCK_FILE)

df_prod, df_map, df_sales, df_stock = load_data()

def get_actual_inventory():
    df_p, df_m, df_sa, df_st = load_data()
    inward_stock = df_p.set_index('Product Code')['QTY'].to_dict()
    for _, row in df_st.iterrows():
        p_code = row['Product Code']
        if p_code in inward_stock: inward_stock[p_code] += row['Added QTY']
            
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
                    if linked_sku in sold_stock: sold_stock[linked_sku] += s_qty
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

# ---- Sidebar Configuration Navigation Panel ----
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
    df_actual = get_actual_inventory()
    
    st.sidebar.write("---")
    st.sidebar.write("### 🎛️ Quick Filters")
    brands = ["All"] + list(df_actual['Brand'].dropna().unique())
    selected_brand = st.sidebar.selectbox("Filter by Brand Name", brands)
    
    types = ["All"] + list(df_actual['Type'].dropna().unique())
    selected_type = st.sidebar.selectbox("Filter by Stock Type", types)
    
    if selected_brand != "All": df_actual = df_actual[df_actual['Brand'] == selected_brand]
    if selected_type != "All": df_actual = df_actual[df_actual['Type'] == selected_type]
        
    # Beautiful OMS-style cards
    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1:
        st.markdown(f'<div class="metric-container card-blue"><div class="metric-title">Unique Master SKUs</div><div class="metric-value">{len(df_actual)}</div></div>', unsafe_allow_html=True)
    with m_col2:
        st.markdown(f'<div class="metric-container card-orange"><div class="metric-title">Total Units Sold Out</div><div class="metric-value">{int(df_actual["Total Sold QTY"].sum())}</div></div>', unsafe_allow_html=True)
    with m_col3:
        st.markdown(f'<div class="metric-container card-green"><div class="metric-title">Available Warehouse Stock</div><div class="metric-value">{int(df_actual["Actual Balance Stock"].sum())}</div></div>', unsafe_allow_html=True)
    
    st.write("---")
    st.subheader("📋 Real-time Multi-channel Inventory Ledger")
    
    # Render with interactive element formatting
    st.dataframe(
        df_actual[["Image URL", "Product Code", "Name", "Color", "Size", "Brand", "Type", "QTY", "Total Sold QTY", "Actual Balance Stock"]], 
        column_config={
            "Image URL": st.column_config.ImageColumn("Preview"),
            "Type": st.column_config.SelectColumn("Strategy Type", options=["SIMPLE", "BUNDLE"])
        },
        use_container_width=True,
        hide_index=True
    )

# ==================== 1. MASTER SKU SHEET ====================
elif menu == "📦 1. MASTER SKU Sheet":
    st.markdown("<h1>📦 Master Inventory Dataset</h1>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["📁 Bulk File Import (Excel/CSV)", "✍️ Manual Single Entry"])
    
    with tab1:
        st.subheader("Bulk Upload Template Sheet")
        uploaded_file = st.file_uploader("Choose File", type=["xlsx", "csv"], key="master_upload")
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
                st.success("New SKU configuration committed successfully!")
                st.rerun()
    st.dataframe(df_prod, use_container_width=True, hide_index=True)

# ==================== 2. CHANEL SKU MAP SHEET ====================
elif menu == "🔗 2. CHANEL SKU MAP Sheet":
    st.markdown("<h1>🔗 Channel Mapping Matrix</h1>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["📁 Bulk Mapping Upload", "✍️ Manual Link"])
    
    with tab1:
        st.subheader("Upload Channel SKU Connection Template")
        uploaded_file = st.file_uploader("Upload Connection file", type=["xlsx", "csv"], key="map_upload")
        if uploaded_file is not None:
            bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            st.dataframe(bulk_df.head(), hide_index=True)
            if st.button("🚀 Sync Link Map Table"):
                bulk_df.to_csv(MAP_FILE, index=False)
                st.success("Mapping configuration linked successfully!")
                st.rerun()
    with tab2:
        with st.form("map_form", clear_on_submit=True):
            c_sku = st.text_input("Seller SKU listed on Channels").strip()
            m_sku = st.text_input("Target Master SKU Code").strip()
            ch_name = st.text_input("Channel Name (e.g. FLIPKART)")
            pack_of = st.selectbox("Pack Config", ["SINGLE", "BUNDLE"])
            brand = st.text_input("BRAND Reference", "VIDA LOCA")
            if st.form_submit_button("Commit Connection Link") and c_sku:
                pd.DataFrame([[c_sku, m_sku, ch_name, pack_of, brand]], columns=df_map.columns).to_csv(MAP_FILE, mode='a', header=False, index=False)
                st.success("Mapping connected successfully!")
                st.rerun()
    st.dataframe(df_map, use_container_width=True, hide_index=True)

# ==================== 3. ADD INVENTORY SHEET ====================
elif menu == "📥 3. ADD INVENTORY Sheet":
    st.markdown("<h1>📥 Stock Inward Ledger</h1>", unsafe_allow_html=True)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with st.form("stock_form", clear_on_submit=True):
        p_code = st.selectbox("Choose Target Active Product Code", df_prod['Product Code'].values if not df_prod.empty else [])
        add_qty = st.number_input("Inward QTY count to append", min_value=1, value=1)
        if st.form_submit_button("Commit Fresh Inventory QTY") and p_code:
            pd.DataFrame([[current_time, p_code, add_qty]], columns=df_stock.columns).to_csv(STOCK_FILE, mode='a', header=False, index=False)
            st.success("Physical warehouse stock updated successfully!")
            st.rerun()
    st.dataframe(df_stock, use_container_width=True, hide_index=True)

# ==================== 4. SALE DATA SHEET ====================
elif menu == "📤 4. SALE DATA Sheet":
    st.markdown("<h1>📤 Channel Sales Manifest</h1>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["📁 Import Marketplace Order Manifest", "✍️ Manual Individual Entry"])
    
    with tab1:
        st.subheader("Upload Daily Dispatched Orders Spreadsheets")
        uploaded_file = st.file_uploader("Upload manifest logs file", type=["xlsx", "csv"], key="sale_upload")
        if uploaded_file is not None:
            bulk_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            st.dataframe(bulk_df.head(), hide_index=True)
            if st.button("🚀 Deduct Mapped Inventory levels"):
                bulk_df.to_csv(SALES_FILE, index=False)
                st.success("Order evaluation complete. Live inventory depleted cleanly!")
                st.rerun()
    with tab2:
        with st.form("sale_form", clear_on_submit=True):
            s_date = st.date_input("Invoice Date").strftime("%Y-%m-%d")
            c_sku = st.text_input("Channel SKU key code")
            brand = st.text_input("BRAND Name Reference", "VIDA LOCA")
            qty = st.number_input("Outward Units QTY", min_value=1, value=1)
            if st.form_submit_button("Commit Manual Sales Entry") and c_sku:
                pd.DataFrame([[s_date, c_sku, brand, qty]], columns=df_sales.columns).to_csv(SALES_FILE, mode='a', header=False, index=False)
                st.success("Sales entry recorded successfully!")
                st.rerun()
    st.dataframe(df_sales, use_container_width=True, hide_index=True)
