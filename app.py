import io
import os
import random
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import barcode
import pandas as pd
import qrcode
import streamlit as st
from barcode.writer import ImageWriter
from PIL import Image
from supabase import Client, create_client

# --- Theme Configuration ---
st.set_page_config(page_title="Vida Loca Advanced ERP", layout="wide")

st.markdown(
    """
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
""",
    unsafe_allow_html=True,
)


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


# --- BARCODE & QR GENERATOR HELPER FUNCTIONS ---
def generate_barcode_img(text):
  code128 = barcode.get_barcode_class("code128")
  rv = io.BytesIO()
  code = code128(text, writer=ImageWriter())
  code.write(rv)
  rv.seek(0)
  return rv


def generate_qrcode_img(text):
  qr = qrcode.QRCode(
      version=1,
      error_correction=qrcode.constants.ERROR_CORRECT_L,
      box_size=10,
      border=4,
  )
  qr.add_data(text)
  qr.make(fit=True)
  img = qr.make_image(fill_color="black", back_color="white")
  rv = io.BytesIO()
  img.save(rv, format="PNG")
  rv.seek(0)
  return rv


# --- ⚡ BULK SUPABASE FETCH WITH MULTITHREADING ENGINE ⚡ ---
def fetch_chunk(table_name, start, limit):
  try:
    res = (
        supabase.table(table_name)
        .select("*")
        .range(start, start + limit - 1)
        .execute()
    )
    return res.data if res.data else []
  except:
    return []


@st.cache_data(
    ttl=300, show_spinner="⚡ Cloud Database se Records Fetch ho rahe hain..."
)
def load_data_cached():

  def fetch_all_rows_multithreaded(table_name):
    try:
      count_res = (
          supabase.table(table_name)
          .select("id", count="exact")
          .limit(1)
          .execute()
      )
      total_rows = count_res.count if count_res.count else 200000
    except:
      total_rows = 600000

    limit = 4000
    ranges = [
        (table_name, i, limit) for i in range(0, total_rows + limit, limit)
    ]

    all_data = []
    with ThreadPoolExecutor(max_workers=20) as executor:
      results = executor.map(lambda p: fetch_chunk(*p), ranges)
      for rows in results:
        if rows:
          all_data.extend(rows)

    return pd.DataFrame(all_data)

  # 1. Master SKU Fetch
  try:
    df_p = fetch_all_rows_multithreaded("master_sku")
    if not df_p.empty:
      actual_cols = [
          "category_code",
          "product_code",
          "name",
          "scan_identifier",
          "color",
          "size",
          "brand",
          "type",
          "component_product_code",
          "qty",
          "image_url",
      ]
      df_p = df_p[[c for c in actual_cols if c in df_p.columns]]
      df_p.columns = [
          "Category Code",
          "Product Code",
          "Name",
          "Scan Identifier",
          "Color",
          "Size",
          "Brand",
          "Type",
          "Component Product Code",
          "QTY",
          "Image URL",
      ][: len(df_p.columns)]
  except:
    df_p = pd.DataFrame()
  if df_p.empty:
    df_p = pd.DataFrame(
        columns=[
            "Category Code",
            "Product Code",
            "Name",
            "Scan Identifier",
            "Color",
            "Size",
            "Brand",
            "Type",
            "Component Product Code",
            "QTY",
            "Image URL",
        ]
    )

  # 2. Mapping Matrix Fetch
  try:
    df_m = fetch_all_rows_multithreaded("channel_sku_map")
    if not df_m.empty:
      df_m = df_m.drop(columns=["id", "created_at"], errors="ignore")
      df_m.columns = [
          "Seller SKU on Channel",
          "SKU Code",
          "channelName",
          "PACK OF",
          "BRAND",
      ][: len(df_m.columns)]
  except:
    df_m = pd.DataFrame()
  if df_m.empty:
    df_m = pd.DataFrame(
        columns=[
            "Seller SKU on Channel",
            "SKU Code",
            "channelName",
            "PACK OF",
            "BRAND",
        ]
    )

  # 3. Sales Fetch
  try:
    df_sa = fetch_all_rows_multithreaded("sale_data")
    if not df_sa.empty:
      df_sa = df_sa.drop(columns=["created_at"], errors="ignore")
      df_sa.columns = [
          "id" if str(c).lower() == "id" else c for c in df_sa.columns
      ]

      rename_dict = {}
      for col in df_sa.columns:
        if col in ["id", "ID"]:
          rename_dict[col] = "ID"
        elif col in ["date", "DATE"]:
          rename_dict[col] = "Date"
        elif col in [
            "channel_sku",
            "CHANNEL_SKU",
            "ITEM SKU CODE",
            "ITEM_SKU_CODE",
            "SKU",
        ]:
          rename_dict[col] = "Channel SKU"
        elif col in ["type", "TYPE"]:
          rename_dict[col] = "Type"
        elif col in ["brand", "BRAND"]:
          rename_dict[col] = "Brand"
        elif col in ["qty", "QTY", "quantity", "QUANTITY"]:
          rename_dict[col] = "Qty"
      df_sa = df_sa.rename(columns=rename_dict)
  except:
    df_sa = pd.DataFrame()
  if df_sa.empty:
    df_sa = pd.DataFrame(
        columns=["ID", "Date", "Channel SKU", "Type", "Brand", "Qty"]
    )

  # 4. Stock Fetch
  try:
    df_st = fetch_all_rows_multithreaded("add_inventory")
    if not df_st.empty:
      df_st = df_st.drop(columns=["created_at"], errors="ignore")
      df_st.columns = [
          "id" if str(c).lower() == "id" else c for c in df_st.columns
      ]
      rename_st = {
          "id": "ID",
          "product_code": "Product Code",
          "added_qty": "Added QTY",
          "brand": "Brand",
      }
      df_st = df_st.rename(columns=rename_st)
      if "Date & Time" not in df_st.columns:
        df_st["Date & Time"] = datetime.now().strftime("%Y-%m-%d")
  except:
    df_st = pd.DataFrame()
  if df_st.empty:
    df_st = pd.DataFrame(
        columns=["ID", "Product Code", "Added QTY", "Brand", "Date & Time"]
    )

  return df_p, df_m, df_sa, df_st


def clear_app_cache():
  st.cache_data.clear()


def clean_sku(val):
  if pd.isna(val):
    return ""
  s = str(val).strip().upper()
  if s.endswith(".0"):
    s = s[:-2]
  return s


def convert_df_to_csv(df):
  return df.to_csv(index=False).encode("utf-8")


# --- INVENTORY LEDGER ENGINE ---
def get_actual_inventory_cached(
    start_date=None, end_date=None, selected_brand="All", ignore_date=False
):
  df_p, df_m, df_sa, df_st = load_data_cached()

  df_p_cp = df_p.copy()
  df_p_cp["Product Code Clean"] = df_p_cp["Product Code"].apply(clean_sku)
  df_p_cp["QTY"] = (
      pd.to_numeric(df_p_cp["QTY"], errors="coerce").fillna(0).astype(int)
  )

  inward_map = {}
  if not df_st.empty:
    df_st_cp = df_st.copy()
    df_st_cp["Product Code Clean"] = df_st_cp["Product Code"].apply(clean_sku)
    df_st_cp["Added QTY"] = (
        pd.to_numeric(df_st_cp["Added QTY"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    if not ignore_date and start_date and end_date:
      try:
        df_st_cp["Parsed_Date"] = pd.to_datetime(
            df_st_cp["Date & Time"], errors="coerce"
        ).dt.date
        df_st_cp = df_st_cp[
            (df_st_cp["Parsed_Date"] >= start_date)
            & (df_st_cp["Parsed_Date"] <= end_date)
        ]
      except:
        pass

    inward_map = (
        df_st_cp.groupby("Product Code Clean")["Added QTY"].sum().to_dict()
    )

  df_p_cp["Inward Log Added"] = (
      df_p_cp["Product Code Clean"].map(inward_map).fillna(0).astype(int)
  )
  df_p_cp["Total Inward Stock"] = df_p_cp["QTY"] + df_p_cp["Inward Log Added"]

  sold_stock = {code: 0 for code in df_p_cp["Product Code Clean"].unique()}

  if not df_sa.empty:
    df_sa_cp = df_sa.copy()
    df_sa_cp["Channel SKU Clean"] = df_sa_cp["Channel SKU"].apply(clean_sku)
    df_sa_cp["Qty"] = (
        pd.to_numeric(df_sa_cp["Qty"], errors="coerce").fillna(0).astype(int)
    )
    df_sa_cp["Type Clean"] = (
        df_sa_cp["Type"].fillna("").astype(str).str.strip().str.upper()
    )

    if not ignore_date and start_date and end_date:
      try:
        df_sa_cp["Parsed_Date"] = pd.to_datetime(
            df_sa_cp["Date"], errors="coerce"
        ).dt.date
        df_sa_cp = df_sa_cp[
            (df_sa_cp["Parsed_Date"] >= start_date)
            & (df_sa_cp["Parsed_Date"] <= end_date)
        ]
      except:
        pass

    if selected_brand != "All" and "Brand" in df_sa_cp.columns:
      df_sa_cp = df_sa_cp[
          df_sa_cp["Brand"].astype(str).str.strip().str.upper()
          == selected_brand.upper()
      ]

    chanel_map = {}
    if not df_m.empty:
      chanel_map = dict(
          zip(
              df_m["Seller SKU on Channel"].apply(clean_sku),
              df_m["SKU Code"].apply(clean_sku),
          )
      )

    df_sa_cp["Mapped SKU"] = (
        df_sa_cp["Channel SKU Clean"]
        .map(chanel_map)
        .fillna(df_sa_cp["Channel SKU Clean"])
    )
    sales_summary = (
        df_sa_cp.groupby(["Mapped SKU", "Type Clean"])["Qty"].sum().reset_index()
    )

    scan_to_comp = dict(
        zip(
            df_p_cp["Scan Identifier"].apply(clean_sku),
            df_p_cp["Component Product Code"].apply(clean_sku),
        )
    )
    comp_to_prod = dict(
        zip(
            df_p_cp["Component Product Code"].apply(clean_sku),
            df_p_cp["Product Code Clean"],
        )
    )

    for _, row in sales_summary.iterrows():
      sku = str(row["Mapped SKU"])
      s_type = str(row["Type Clean"])
      qty = int(row["Qty"])

      if s_type in ["BUNDAL", "BUNDLE"]:
        comp_sku = scan_to_comp.get(sku, "")
        if comp_sku in sold_stock:
          sold_stock[comp_sku] += qty
      else:
        if sku in sold_stock:
          sold_stock[sku] += qty
        else:
          alt_sku = comp_to_prod.get(sku, "")
          if alt_sku in sold_stock:
            sold_stock[alt_sku] += qty

  df_p_cp["Total Sold QTY"] = (
      df_p_cp["Product Code Clean"].map(sold_stock).fillna(0).astype(int)
  )
  df_p_cp["Actual Balance Stock"] = (
      df_p_cp["Total Inward Stock"] - df_p_cp["Total Sold QTY"]
  )

  if selected_brand != "All" and "Brand" in df_p_cp.columns:
    df_p_cp = df_p_cp[
        df_p_cp["Brand"].astype(str).str.strip().str.upper()
        == selected_brand.upper()
    ]

  return df_p_cp


# ---- Sidebar Panel ----
st.sidebar.markdown(
    "<h2 style='color:white; text-align:center;'>Vida Loca Hub</h2>",
    unsafe_allow_html=True,
)
if st.sidebar.button("🔄 Refresh Data (Clear Cache)"):
  clear_app_cache()
  st.rerun()

st.sidebar.write("---")
menu = st.sidebar.radio(
    "📌 CONTROL PANEL:", [
        "📊 Live Dashboard",
        "🔄 Live Channels Sync",
        "📦 1. MASTER SKU Sheet",
        "🔗 2. CHANEL SKU MAP Sheet",
        "📥 3. ADD INVENTORY Sheet",
        "📤 4. SALE DATA Sheet",
    ]
)

df_prod, df_map, df_sales, df_stock = load_data_cached()

# ==================== LIVE DASHBOARD ====================
if menu == "📊 Live Dashboard":
  st.markdown(
      "<h1 style='color:#0f172a;'>📊 OMS Core Dashboard</h1>",
      unsafe_allow_html=True,
  )
  today = date.today()
  start_d = st.sidebar.date_input("Start Date", date(today.year, 1, 1))
  end_d = st.sidebar.date_input("End Date", today)
  ignore_date = st.sidebar.checkbox(
      "Ignore Date Filter (Show All-Time Sales)", value=True
  )

  all_brands = ["All"]
  if not df_sales.empty and "Brand" in df_sales.columns:
    all_brands += sorted(
        list(
            df_sales["Brand"]
            .dropna()
            .astype(str)
            .str.strip()
            .str.upper()
            .unique()
        )
    )

  all_brands = sorted(list(set(all_brands)), key=lambda x: (x != "All", x))
  selected_brand = st.sidebar.selectbox("Filter by Brand Name", all_brands)

  df_actual = get_actual_inventory_cached(
      start_date=start_d,
      end_date=end_d,
      selected_brand=selected_brand,
      ignore_date=ignore_date,
  )

  if not df_sales.empty:
    df_sales_filtered = df_sales.copy()
    df_sales_filtered["Qty"] = (
        pd.to_numeric(df_sales_filtered["Qty"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    if not ignore_date:
      try:
        df_sales_filtered["Parsed_Date"] = pd.to_datetime(
            df_sales_filtered["Date"], errors="coerce"
        ).dt.date
        df_sales_filtered = df_sales_filtered[
            (df_sales_filtered["Parsed_Date"] >= start_d)
            & (df_sales_filtered["Parsed_Date"] <= end_d)
        ]
      except:
        pass

    if selected_brand != "All" and "Brand" in df_sales_filtered.columns:
      df_sales_filtered = df_sales_filtered[
          df_sales_filtered["Brand"].astype(str).str.strip().str.upper()
          == selected_brand.upper()
      ]

    total_sales_display = int(df_sales_filtered["Qty"].sum())
  else:
    total_sales_display = 0

  m_col1, m_col2, m_col3 = st.columns(3)
  with m_col1:
    st.markdown(
        '<div class="metric-container card-blue"><div'
        ' class="metric-title">Total Inward Stock</div><div'
        ' class="metric-value">'
        f'{int(df_actual["Total Inward Stock"].sum()) if "Total Inward Stock" in df_actual.columns else 0}</div></div>',
        unsafe_allow_html=True,
    )
  with m_col2:
    st.markdown(
        '<div class="metric-container card-orange"><div'
        ' class="metric-title">Total Sale QTY</div><div'
        ' class="metric-value">'
        f"{total_sales_display}</div></div>",
        unsafe_allow_html=True,
    )
  with m_col3:
    st.markdown(
        '<div class="metric-container card-green"><div'
        ' class="metric-title">Actual Balance Stock</div><div'
        ' class="metric-value">'
        f'{int(df_actual["Actual Balance Stock"].sum()) if "Actual Balance Stock" in df_actual.columns else 0}</div></div>',
        unsafe_allow_html=True,
    )

  st.write("---")
  st.subheader("📋 Inventory Ledger Table")
  show_cols = [
      "Image URL",
      "Product Code",
      "Name",
      "Color",
      "Size",
      "Brand",
      "Type",
      "Total Inward Stock",
      "Total Sold QTY",
      "Actual Balance Stock",
  ]
  available_show = [c for c in show_cols if c in df_actual.columns]
  st.dataframe(
      df_actual[available_show],
      column_config={"Image URL": st.column_config.ImageColumn("Preview")},
      use_container_width=True,
      hide_index=True,
  )

# ==================== 📥 3. ADD INVENTORY SHEET (WITH AUTO-SCAN & BULK CODE GENERATION) ====================
elif menu == "📥 3. ADD INVENTORY Sheet":
  st.markdown(
      "<h1>📥 Stock Inward Ledger & Barcode Engine</h1>", unsafe_allow_html=True
  )

  if not df_stock.empty:
    st.download_button(
        label="📥 Download Complete Stock Inward Ledger (CSV)",
        data=convert_df_to_csv(df_stock),
        file_name=f"Stock_Inward_Full_{date.today()}.csv",
        mime="text/csv",
        key="download_stock_full",
    )

  tab1, tab2, tab3 = st.tabs([
      "📸 Auto-Push Scan & Inward",
      "🖨️ Bulk Barcode & QR Generator",
      "📁 Bulk Manifest Upload",
  ])

  # TAB 1: AUTO-PUSH SCANNER
  with tab1:
    st.subheader("📷 Automatic Scanner (Auto-Push to Inventory)")
    st.caption(
        "💡 **Tip:** Barcode gun se scan karne par item automatically database"
        " me push ho jayega."
    )

    brand_options = (
        sorted(list(df_prod["Brand"].dropna().unique()))
        if not df_prod.empty and "Brand" in df_prod.columns
        else ["VIDA LOCA", "YUGNIK"]
    )
    selected_inward_brand = st.selectbox(
        "🏷️ Select Brand for Inward", brand_options, key="auto_scan_brand"
    )

    scan_qty = st.number_input(
        "Quantity per Scan",
        min_value=1,
        value=1,
        step=1,
        key="auto_scan_qty",
    )

    # Callback function for automatic execution when barcode scanner sends Enter key
    def handle_auto_scan():
      code = st.session_state.auto_scanned_code.strip().upper()
      if code:
        try:
          supabase.table("add_inventory").insert({
              "product_code": code,
              "added_qty": int(scan_qty),
              "brand": str(selected_inward_brand).strip().upper(),
          }).execute()
          clear_app_cache()
          st.toast(
              f"✅ Auto-Added: {scan_qty} Qty of '{code}' to"
              f" {selected_inward_brand}!",
              icon="🚀",
          )
          st.session_state.auto_scanned_code = ""  # Clear box after scan
        except Exception as e:
          st.error(f"Database Error: {e}")

    st.text_input(
        "⚡ Focus cursor here and scan SKU (Auto Push on Scan)",
        key="auto_scanned_code",
        on_change=handle_auto_scan,
    )

  # TAB 2: BULK BARCODE & QR GENERATOR
  with tab2:
    st.subheader("🖨️ Bulk Barcode & QR Code Generator (ZIP Download)")

    gen_mode = st.radio(
        "Select SKU Input Source",
        [
            "Select Master SKUs from Database",
            "Upload Bulk SKU List (CSV/Excel)",
        ],
        horizontal=True,
    )
    skus_to_generate = []

    if gen_mode == "Select Master SKUs from Database":
      p_code_list = (
          sorted(list(df_prod["Product Code"].dropna().unique()))
          if not df_prod.empty
          else []
      )
      skus_to_generate = st.multiselect(
          "Choose SKUs to Generate Codes", p_code_list
      )
    else:
      sku_file = st.file_uploader(
          "Upload CSV/Excel containing 'Product Code' column",
          type=["csv", "xlsx"],
          key="bulk_sku_file",
      )
      if sku_file is not None:
        file_df = (
            pd.read_csv(sku_file)
            if sku_file.name.endswith(".csv")
            else pd.read_excel(sku_file)
        )
        col_found = None
        for col in file_df.columns:
          if "product" in str(col).lower() or "sku" in str(col).lower():
            col_found = col
            break
        if col_found:
          skus_to_generate = (
              file_df[col_found].dropna().astype(str).str.strip().tolist()
          )
          st.success(
              f"✅ Extracted {len(skus_to_generate)} SKUs from column"
              f" '{col_found}'"
          )
        else:
          st.error("Pehle column me SKU / Product Code naam ka header ho!")

    col_btn1, col_btn2 = st.columns(2)

    if skus_to_generate:
      with col_btn1:
        if st.button("📦 Generate Bulk Barcodes (ZIP)"):
          zip_buffer = io.BytesIO()
          with zipfile.ZipFile(
              zip_buffer, "a", zipfile.ZIP_DEFLATED, False
          ) as zip_file:
            for sku in skus_to_generate:
              clean_s = str(sku).strip().upper()
              b_img = generate_barcode_img(clean_s)
              zip_file.writestr(f"Barcode_{clean_s}.png", b_img.getvalue())
          zip_buffer.seek(0)
          st.download_button(
              label="📥 Download Barcodes ZIP Archive",
              data=zip_buffer,
              file_name=f"Barcodes_Bulk_{date.today()}.zip",
              mime="application/zip",
          )

      with col_btn2:
        if st.button("📱 Generate Bulk QR Codes (ZIP)"):
          zip_buffer = io.BytesIO()
          with zipfile.ZipFile(
              zip_buffer, "a", zipfile.ZIP_DEFLATED, False
          ) as zip_file:
            for sku in skus_to_generate:
              clean_s = str(sku).strip().upper()
              q_img = generate_qrcode_img(clean_s)
              zip_file.writestr(f"QRCode_{clean_s}.png", q_img.getvalue())
          zip_buffer.seek(0)
          st.download_button(
              label="📥 Download QR Codes ZIP Archive",
              data=zip_buffer,
              file_name=f"QRCodes_Bulk_{date.today()}.zip",
              mime="application/zip",
          )

  # TAB 3: BULK LOAD
  with tab3:
    st.subheader("Upload Bulk Inventory Log Sheet")
    uploaded_inv_file = st.file_uploader(
        "Choose manifest file", type=["xlsx", "csv"], key="inv_bulk"
    )
    if uploaded_inv_file is not None:
      bulk_inv_df = (
          pd.read_csv(uploaded_inv_file)
          if uploaded_inv_file.name.endswith(".csv")
          else pd.read_excel(uploaded_inv_file)
      )
      if st.button("🚀 Process Bulk Stock Load"):
        try:
          bulk_inv_df.columns = ["product_code", "added_qty", "brand"][: len(
              bulk_inv_df.columns
          )]
          supabase.table("add_inventory").insert(
              bulk_inv_df.to_dict(orient="records")
          ).execute()
          clear_app_cache()
          st.success("Inventory Bulk Logs Added Successfully!")
          st.rerun()
        except Exception as e:
          st.error(f"Error processing upload: {e}")

  st.write("---")
  cols_to_view = [
      c
      for c in ["ID", "Product Code", "Added QTY", "Brand", "Date & Time"]
      if c in df_stock.columns
  ]
  st.dataframe(df_stock[cols_to_view], use_container_width=True, hide_index=True)

# ==================== 📤 4. SALE DATA SHEET (WITH AUTO SCAN) ====================
elif menu == "📤 4. SALE DATA Sheet":
  st.markdown(
      "<h1>📤 Channel Sales Manifest Database Control</h1>",
      unsafe_allow_html=True,
  )

  if not df_sales.empty:
    st.download_button(
        label="📥 Download Complete Channel Sales Manifest (CSV)",
        data=convert_df_to_csv(df_sales),
        file_name=f"Sales_Manifest_Full_{date.today()}.csv",
        mime="text/csv",
        key="download_sales_full",
    )

  s_tab1, s_tab2, s_tab3 = st.tabs([
      "📸 Auto-Push Scan & Add Sale",
      "✍️ Manual Single Entry Mode",
      "📁 Bulk Sales Sheet Upload",
  ])

  # TAB 1: AUTO-PUSH SCAN SALE
  with s_tab1:
    st.subheader("📷 Auto-Push Scanner for Channel Direct Sale")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
      scan_sale_type = st.selectbox(
          "Order Type", ["SINGLE", "BUNDLE", "BUNDAL"], key="auto_sale_type"
      )
      scan_sale_brand = st.selectbox(
          "Brand Name", ["VIDA LOCA", "YUGNIK"], key="auto_sale_brand"
      )
    with col_s2:
      scan_sale_qty = st.number_input(
          "Qty Sold", min_value=1, value=1, step=1, key="auto_sale_qty"
      )
      scan_sale_date = st.date_input(
          "Order Date", date.today(), key="auto_sale_date"
      )

    def handle_auto_sale_scan():
      code = st.session_state.auto_sale_code.strip().upper()
      if code:
        try:
          sale_payload = {
              "date": scan_sale_date.strftime("%Y-%m-%d"),
              "channel_sku": code,
              "type": str(scan_sale_type).strip().upper(),
              "brand": str(scan_sale_brand).strip().upper(),
              "qty": int(scan_sale_qty),
          }
          supabase.table("sale_data").insert(sale_payload).execute()
          clear_app_cache()
          st.toast(
              f"✅ Sale Deducted! {scan_sale_qty} Qty of '{code}'", icon="📦"
          )
          st.session_state.auto_sale_code = ""
        except Exception as e:
          st.error(f"Database Error: {e}")

    st.text_input(
        "⚡ Focus cursor here and scan Channel SKU Barcode",
        key="auto_sale_code",
        on_change=handle_auto_sale_scan,
    )

  # TAB 2: MANUAL ENTRY
  with s_tab2:
    st.subheader("Add Single Channel Sale Record")
    with st.form("single_sale_form", clear_on_submit=True):
      col_s1, col_s2 = st.columns(2)
      with col_s1:
        sale_date = st.date_input("Order Date", date.today())
        channel_sku_list = (
            sorted(list(df_map["Seller SKU on Channel"].dropna().unique()))
            if not df_map.empty
            else []
        )
        s_sku = st.selectbox("Select Channel SKU", channel_sku_list) if channel_sku_list else st.text_input("Enter Channel SKU").strip().upper()
        s_type = st.selectbox("Order Type", ["SINGLE", "BUNDLE", "BUNDAL"])
      with col_s2:
        s_brand = st.selectbox("Brand Name", ["VIDA LOCA", "YUGNIK"])
        s_qty = st.number_input(
            "Order Quantity (Qty)", min_value=1, value=1, step=1
        )

      submit_sale_single = st.form_submit_button("🚀 Insert Sale Record")

      if submit_sale_single and s_sku != "":
        try:
          sale_payload = {
              "date": sale_date.strftime("%Y-%m-%d"),
              "channel_sku": str(s_sku).strip().upper(),
              "type": str(s_type).strip().upper(),
              "brand": str(s_brand).strip().upper(),
              "qty": int(s_qty),
          }
          supabase.table("sale_data").insert(sale_payload).execute()
          clear_app_cache()
          st.success(f"Order Manifest Linked successfully for {s_sku}!")
          st.rerun()
        except Exception as e:
          st.error(f"Database Error: {e}")

  # TAB 3: BULK UPLOAD
  with s_tab3:
    st.subheader("Upload Bulk Channel Sales Sheet")
    uploaded_sale_file = st.file_uploader(
        "Choose sales file", type=["xlsx", "csv"], key="sales_bulk"
    )

    if uploaded_sale_file is not None:
      bulk_sales_df = (
          pd.read_csv(uploaded_sale_file)
          if uploaded_sale_file.name.endswith(".csv")
          else pd.read_excel(uploaded_sale_file)
      )
      if st.button("🚀 Process Bulk Sales Upload"):
        try:
          bulk_sales_df.columns = [
              str(c).strip().lower() for c in bulk_sales_df.columns
          ]
          rename_bulk = {}
          for c in bulk_sales_df.columns:
            if "date" in c:
              rename_bulk[c] = "date"
            elif "sku" in c:
              rename_bulk[c] = "channel_sku"
            elif "type" in c:
              rename_bulk[c] = "type"
            elif "brand" in c:
              rename_bulk[c] = "brand"
            elif "qty" in c or "quantity" in c:
              rename_bulk[c] = "qty"

          bulk_sales_df = bulk_sales_df.rename(columns=rename_bulk)
          needed_cols = ["date", "channel_sku", "type", "brand", "qty"]
          bulk_sales_df = bulk_sales_df[
              [col for col in needed_cols if col in bulk_sales_df.columns]
          ]

          if "date" in bulk_sales_df.columns:
            bulk_sales_df["date"] = pd.to_datetime(
                bulk_sales_df["date"], errors="coerce"
            ).dt.strftime("%Y-%m-%d")

          sales_records = bulk_sales_df.to_dict(orient="records")
          supabase.table("sale_data").insert(sales_records).execute()
          clear_app_cache()
          st.success("Bulk Sales Records Synchronized Successfully!")
          st.rerun()
        except Exception as e:
          st.error(f"Upload Error: {e}")

  st.write("---")
  cols_to_display = [
      c
      for c in ["ID", "Date", "Channel SKU", "Type", "Brand", "Qty"]
      if c in df_sales.columns
  ]
  st.dataframe(
      df_sales[cols_to_display], use_container_width=True, hide_index=True
  )

# ==================== OTHER PANELS ====================
elif menu == "🔄 Live Channels Sync":
  st.markdown(
      "<h1>🔄 Live Channel Marketplace Integrations</h1>",
      unsafe_allow_html=True,
  )
  st.dataframe(df_sales.tail(15), use_container_width=True, hide_index=True)
elif menu == "📦 1. MASTER SKU Sheet":
  st.markdown(
      "<h1>📦 Master Inventory DB Records</h1>", unsafe_allow_html=True
  )
  st.dataframe(df_prod, use_container_width=True, hide_index=True)
elif menu == "🔗 2. CHANEL SKU MAP Sheet":
  st.markdown(
      "<h1>🔗 Channel Mapping Matrix DB</h1>", unsafe_allow_html=True
  )
  st.dataframe(df_map, use_container_width=True, hide_index=True)
