from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import io
import os
import random
import zipfile

import barcode
from barcode.writer import ImageWriter
import pandas as pd
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.platypus import Image as RLImage
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
import streamlit as st
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


# --- HIGH RESOLUTION BARCODE & QR GENERATOR ---
def generate_barcode_img(text):
    code128 = barcode.get_barcode_class("code128")
    rv = io.BytesIO()
    writer_options = {
        "module_height": 10.0,
        "quiet_zone": 2.0,
        "font_size": 10,
        "text_distance": 3.0,
        "write_text": True,
        "dpi": 300,
    }
    code = code128(text, writer=ImageWriter())
    code.write(rv, options=writer_options)
    rv.seek(0)
    return rv


def generate_qrcode_img(text):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    rv = io.BytesIO()
    img.save(rv, format="PNG")
    rv.seek(0)
    return rv


# --- PDF GENERATOR HELPER FUNCTION ---
def generate_codes_pdf(sku_qty_dict, code_type="barcode"):
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=10,
        leftMargin=10,
        topMargin=15,
        bottomMargin=15,
    )

    elements = []
    data_matrix = []
    current_row = []

    cols = 3
    img_w = 2.4 * inch
    img_h = 1.0 * inch if code_type == "barcode" else 1.8 * inch

    expanded_sku_list = []
    for sku, qty in sku_qty_dict.items():
        clean_sku = str(sku).strip().upper()
        try:
            count = int(qty)
        except:
            count = 1
        expanded_sku_list.extend([clean_sku] * max(1, count))

    for clean_s in expanded_sku_list:
        if code_type == "barcode":
            img_stream = generate_barcode_img(clean_s)
        else:
            img_stream = generate_qrcode_img(clean_s)

        rl_img = RLImage(img_stream, width=img_w, height=img_h)
        current_row.append(rl_img)

        if len(current_row) == cols:
            data_matrix.append(current_row)
            current_row = []

    if current_row:
        while len(current_row) < cols:
            current_row.append("")
        data_matrix.append(current_row)

    if data_matrix:
        t = Table(data_matrix, colWidths=[2.55 * inch] * cols)
        t.setStyle(
            TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        elements.append(t)

    doc.build(elements)
    pdf_buffer.seek(0)
    return pdf_buffer


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


# --- SMART SCAN TO MASTER SKU RESOLVER ---
def resolve_to_master_sku(scanned_code, df_master, df_mapping):
    clean_input = clean_sku(scanned_code)
    if not clean_input:
        return ""

    if not df_master.empty:
        if "Product Code" in df_master.columns:
            match = df_master[
                df_master["Product Code"].apply(clean_sku) == clean_input
            ]
            if not match.empty:
                return match.iloc[0]["Product Code"]

        if "Scan Identifier" in df_master.columns:
            match = df_master[
                df_master["Scan Identifier"].apply(clean_sku) == clean_input
            ]
            if not match.empty:
                return match.iloc[0]["Product Code"]

        if "Component Product Code" in df_master.columns:
            match = df_master[
                df_master["Component Product Code"].apply(clean_sku)
                == clean_input
            ]
            if not match.empty:
                return match.iloc[0]["Product Code"]

    if not df_mapping.empty and "Seller SKU on Channel" in df_mapping.columns:
        match_map = df_mapping[
            df_mapping["Seller SKU on Channel"].apply(clean_sku) == clean_input
        ]
        if not match_map.empty:
            mapped_sku = clean_sku(match_map.iloc[0]["SKU Code"])
            return resolve_to_master_sku(mapped_sku, df_master, pd.DataFrame())

    return clean_input


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
        df_st_cp["Product Code Clean"] = df_st_cp["Product Code"].apply(
            clean_sku
        )
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
            df_st_cp.groupby("Product Code Clean")["Added QTY"]
            .sum()
            .to_dict()
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
            pd.to_numeric(df_sa_cp["Qty"], errors="coerce")
            .fillna(0)
            .astype(int)
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
            df_sa_cp.groupby(["Mapped SKU", "Type Clean"])["Qty"]
            .sum()
            .reset_index()
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
        "📦 3. ADD INVENTORY Sheet",
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

# ==================== 📥 3. ADD INVENTORY SHEET ====================
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

    with tab1:
        st.subheader("📷 Automatic Scanner (Auto-Push to Master SKU Inventory)")
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

        def handle_auto_scan():
            raw_code = st.session_state.auto_scanned_code.strip()
            if raw_code:
                master_sku = resolve_to_master_sku(raw_code, df_prod, df_map)
                try:
                    supabase.table("add_inventory").insert({
                        "product_code": master_sku,
                        "added_qty": int(scan_qty),
                        "brand": str(selected_inward_brand).strip().upper(),
                    }).execute()
                    clear_app_cache()
                    st.toast(
                        f"✅ Mapped & Added: {scan_qty} Qty of Master SKU '{master_sku}'",
                        icon="🚀",
                    )
                    st.session_state.auto_scanned_code = ""
                except Exception as e:
                    st.error(f"Database Error: {e}")

        st.text_input(
            "⚡ Focus cursor here and scan Barcode / QR Code",
            key="auto_scanned_code",
            on_change=handle_auto_scan,
        )

    with tab2:
        st.subheader("🖨️ Bulk Barcode & QR Generator")
        p_code_list = (
            sorted(list(df_prod["Product Code"].dropna().unique()))
            if not df_prod.empty
            else []
        )
        selected_skus = st.multiselect(
            "Choose Master SKUs to Generate Codes", p_code_list
        )
        sku_qty_map = {}
        if selected_skus:
            for sku in selected_skus:
                sku_qty_map[sku] = 1

        if sku_qty_map:
            pdf_barcode_bytes = generate_codes_pdf(
                sku_qty_map, code_type="barcode"
            )
            st.download_button(
                label="📄 Download Barcodes PDF Label Sheet",
                data=pdf_barcode_bytes,
                file_name=f"Barcodes_Labels_{date.today()}.pdf",
                mime="application/pdf",
            )

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
                    bulk_inv_df.columns = ["product_code", "added_qty", "brand"][
                        : len(bulk_inv_df.columns)
                    ]
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

# ==================== 📤 4. SALE DATA SHEET ====================
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

    s_tab1, s_tab2 = st.tabs([
        "📸 Auto-Push Scan & Add Sale",
        "📁 Bulk Sales Sheet Upload",
    ])

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
            raw_code = st.session_state.auto_sale_code.strip()
            if raw_code:
                target_sku = resolve_to_master_sku(raw_code, df_prod, df_map)
                try:
                    sale_payload = {
                        "date": scan_sale_date.strftime("%Y-%m-%d"),
                        "channel_sku": target_sku,
                        "type": str(scan_sale_type).strip().upper(),
                        "brand": str(scan_sale_brand).strip().upper(),
                        "qty": int(scan_sale_qty),
                    }
                    supabase.table("sale_data").insert(sale_payload).execute()
                    clear_app_cache()
                    st.toast(
                        f"✅ Sale Deducted! {scan_sale_qty} Qty of Master SKU '{target_sku}'",
                        icon="📦",
                    )
                    st.session_state.auto_sale_code = ""
                except Exception as e:
                    st.error(f"Database Error: {e}")

        st.text_input(
            "⚡ Focus cursor here and scan Channel/Master SKU Barcode",
            key="auto_sale_code",
            on_change=handle_auto_sale_scan,
        )

    with s_tab2:
        st.subheader("Upload Bulk Sales Sheet")
        uploaded_sale_file = st.file_uploader(
            "Choose sales file", type=["xlsx", "csv"], key="sale_bulk"
        )
        if uploaded_sale_file is not None:
            bulk_sale_df = (
                pd.read_csv(uploaded_sale_file)
                if uploaded_sale_file.name.endswith(".csv")
                else pd.read_excel(uploaded_sale_file)
            )
            if st.button("🚀 Process Bulk Sales Load"):
                try:
                    supabase.table("sale_data").insert(
                        bulk_sale_df.to_dict(orient="records")
                    ).execute()
                    clear_app_cache()
                    st.success("Sales Bulk Logs Added Successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error processing upload: {e}")

    st.write("---")
    cols_to_view_s = [
        c
        for c in ["ID", "Date", "Channel SKU", "Type", "Brand", "Qty"]
        if c in df_sales.columns
    ]
    st.dataframe(
        df_sales[cols_to_view_s], use_container_width=True, hide_index=True
    )
