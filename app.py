import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from datetime import datetime, date
import uuid
import pytz
from streamlit_gsheets import GSheetsConnection

# Timezone Indonesia (WIB = UTC+7)
WIB = pytz.timezone("Asia/Jakarta")

def now_wib() -> datetime:
    """Kembalikan waktu saat ini dalam timezone WIB."""
    return datetime.now(tz=WIB)

def today_wib() -> date:
    """Kembalikan tanggal hari ini dalam timezone WIB."""
    return now_wib().date()

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Martabak Finance Tracker",
    page_icon="MFT",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
WORKSHEET_NAME = "Transaksi"
# Kolom Status ditambahkan di akhir untuk backward compatibility
COLUMNS = [
    "ID Transaksi", "Tanggal", "Jam", "Jenis", "Kategori",
    "Detail", "Qty", "Nominal", "Metode", "Status",
]
# Kolom yang ditampilkan di UI (tanpa Status — tersembunyi dari user biasa)
DISPLAY_COLUMNS = ["ID Transaksi", "Tanggal", "Jam", "Jenis", "Kategori", "Detail", "Qty", "Nominal", "Metode"]

JENIS_OPTIONS = ["Pemasukan (Penjualan)", "Pengeluaran (Operasional/Bahan Baku)"]
KATEGORI_PEMASUKAN = [
    "Martabak Manis",
    "Martabak Telor",
    "Martabak Mini",
    "Takoyaki",
    "Otak-otak",
    "Nugget",
    "Basreng",
    "Lain-lain",
]
KATEGORI_PENGELUARAN = [
    "Bahan Baku",
    "Gas",
    "Listrik",
    "Gaji Karyawan",
    "Sewa Tempat",
    "Lain-lain",
]
METODE_OPTIONS = ["Tunai", "QRIS / Transfer", "Debit"]
STATUS_AKTIF = "Aktif"
STATUS_VOID   = "Void"

# ─────────────────────────────────────────────
# HELPERS — Google Sheets
# ─────────────────────────────────────────────

@st.cache_resource(ttl=3600)
def _get_gspread_spreadsheet():
    """
    Buat koneksi gspread langsung menggunakan credentials dari st.secrets.
    Di-cache 1 jam supaya tidak re-auth setiap request.
    Pendekatan ini independen dari versi internal streamlit-gsheets.
    """
    secrets = st.secrets["connections"]["gsheets"]
    spreadsheet_url = secrets["spreadsheet"]

    # Ambil field credentials service account (filter key non-credential)
    cred_fields = [
        "type", "project_id", "private_key_id", "private_key",
        "client_email", "client_id", "auth_uri", "token_uri",
        "auth_provider_x509_cert_url", "client_x509_cert_url",
    ]
    creds_info = {k: secrets[k] for k in cred_fields if k in secrets}
    creds_info.setdefault("type", "service_account")

    gc = gspread.service_account_from_dict(creds_info)
    return gc.open_by_url(spreadsheet_url)


def _get_ws() -> gspread.Worksheet:
    """
    Kembalikan objek gspread.Worksheet secara langsung.
    Digunakan untuk operasi append/update/find yang efisien
    tanpa membaca ulang seluruh data (O(1), bukan O(n)).
    """
    return _get_gspread_spreadsheet().worksheet(WORKSHEET_NAME)


def load_data(ttl: int = 60, include_void: bool = False) -> pd.DataFrame:
    """
    Load data dari Google Sheets via cache.
    - include_void=False  → hanya baris Status='Aktif' (default)
    - include_void=True   → tampilkan semua termasuk yang sudah di-void
    Backward compatible: sheet lama tanpa kolom Jam / Status tetap bisa dibaca.
    """
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet=WORKSHEET_NAME, ttl=ttl)
        if df is None or df.empty:
            return pd.DataFrame(columns=COLUMNS)

        # Pastikan semua kolom ada (backward compat)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None

        df = df[COLUMNS].copy()
        df["Tanggal"] = pd.to_datetime(df["Tanggal"], errors="coerce", dayfirst=True).dt.date
        df["Qty"]     = pd.to_numeric(df["Qty"], errors="coerce").fillna(0).astype(int)
        df["Nominal"] = pd.to_numeric(df["Nominal"], errors="coerce").fillna(0)
        df["Jam"]     = df["Jam"].fillna("").astype(str)
        df["Status"]  = df["Status"].fillna(STATUS_AKTIF).astype(str)

        df = df.dropna(subset=["ID Transaksi"])

        if not include_void:
            df = df[df["Status"] != STATUS_VOID]

        return df
    except Exception as e:
        st.error(f"Gagal memuat data dari Google Sheets: {e}")
        return pd.DataFrame(columns=COLUMNS)


def append_row_fast(row: dict):
    """
    EFISIEN: Append 1 baris langsung ke sheet via gspread API.
    Tidak membaca/menulis ulang seluruh data (O(1), bukan O(n)).
    """
    ws = _get_ws()
    values = [str(row.get(col, "")) for col in COLUMNS]
    ws.append_row(values, value_input_option="USER_ENTERED")
    st.cache_data.clear()


def void_transaction(tx_id: str) -> bool:
    """
    Tandai transaksi sebagai Void dengan mengupdate hanya sel Status-nya.
    Tidak menulis ulang seluruh sheet.
    """
    try:
        ws = _get_ws()
        cell = ws.find(tx_id, in_column=1)  # cari di kolom A (ID Transaksi)
        if cell is None:
            return False
        status_col_idx = COLUMNS.index("Status") + 1  # 1-indexed untuk gspread
        ws.update_cell(cell.row, status_col_idx, STATUS_VOID)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Gagal void transaksi: {e}")
        return False


def update_transaction(tx_id: str, updated_row: dict) -> bool:
    """
    Koreksi transaksi: update seluruh baris berdasarkan TX ID.
    Hanya menulis 1 baris di Sheets, tidak membaca/menulis seluruh data.
    """
    try:
        ws = _get_ws()
        cell = ws.find(tx_id, in_column=1)
        if cell is None:
            return False
        values = [[str(updated_row.get(col, "")) for col in COLUMNS]]
        end_col = chr(ord("A") + len(COLUMNS) - 1)  # 'J' untuk 10 kolom
        ws.update(f"A{cell.row}:{end_col}{cell.row}", values)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Gagal mengupdate transaksi: {e}")
        return False


def format_rupiah(value: float) -> str:
    return f"Rp {value:,.0f}".replace(",", ".")


def format_tanggal(d) -> str:
    """Format tanggal ke format Indonesia: DD/MM/YYYY"""
    if d is None:
        return ""
    if isinstance(d, str):
        try:
            d = pd.to_datetime(d).date()
        except Exception:
            return d
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d)


# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────
if "confirm_void_id" not in st.session_state:
    st.session_state.confirm_void_id = None
if "edit_tx_id" not in st.session_state:
    st.session_state.edit_tx_id = None


# ─────────────────────────────────────────────
# SIDEBAR NAVIGATION
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("MFT")
    st.caption("Martabak Finance Tracker")
    st.divider()

    menu = st.radio(
        "Navigasi",
        options=["Form Keuangan", "View Data", "Dashboard"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("© 2026 MFT · v1.1")


# ─────────────────────────────────────────────
# PAGE 1 — FORM KEUANGAN
# ─────────────────────────────────────────────
if menu == "Form Keuangan":
    st.title("Form Keuangan")
    st.caption("Catat transaksi harian gerai martabak Anda")
    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        jenis = st.selectbox("Jenis Transaksi", options=JENIS_OPTIONS)
    with col2:
        if jenis == "Pemasukan (Penjualan)":
            kategori = st.selectbox("Kategori Produk", options=KATEGORI_PEMASUKAN)
        else:
            kategori = st.selectbox("Kategori Pengeluaran", options=KATEGORI_PENGELUARAN)

    with st.form("form_transaksi", clear_on_submit=True):
        col4, col5, col6 = st.columns(3)
        with col4:
            tanggal = st.date_input("Tanggal Transaksi", value=today_wib())
        with col5:
            jam = st.time_input("Jam Transaksi", value=now_wib().time(), step=60)
        with col6:
            metode = st.selectbox("Metode Pembayaran", options=METODE_OPTIONS)

        detail = st.text_input(
            "Detail / Varian Rasa",
            placeholder="Contoh: Cokelat Keju Spesial, Beli Terigu 5kg...",
        )

        col7, col8 = st.columns([1, 2])
        with col7:
            qty = st.number_input("Jumlah (Qty)", min_value=1, value=1, step=1)
        with col8:
            nominal = st.number_input(
                "Nominal Total (Rp)", min_value=0, value=0, step=1000, format="%d"
            )

        submitted = st.form_submit_button("Simpan Transaksi", use_container_width=True, type="primary")

    if submitted:
        errors = []
        if not detail.strip():
            errors.append("Detail / Varian Rasa tidak boleh kosong.")
        if nominal <= 0:
            errors.append("Nominal harus lebih dari 0.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            jenis_clean = "Pemasukan" if "Pemasukan" in jenis else "Pengeluaran"
            tx_id = "TX-" + now_wib().strftime("%Y%m%d%H%M%S") + "-" + str(uuid.uuid4())[:4].upper()

            row = {
                "ID Transaksi": tx_id,
                "Tanggal":      tanggal.strftime("%d/%m/%Y"),
                "Jam":          jam.strftime("%H:%M"),
                "Jenis":        jenis_clean,
                "Kategori":     kategori,
                "Detail":       detail.strip(),
                "Qty":          qty,
                "Nominal":      nominal,
                "Metode":       metode,
                "Status":       STATUS_AKTIF,
            }

            with st.spinner("Menyimpan ke Google Sheets..."):
                try:
                    append_row_fast(row)
                    st.success(
                        f"Transaksi {tx_id} berhasil disimpan — "
                        f"{jenis_clean} · {format_rupiah(nominal)} · {format_tanggal(tanggal)} {jam.strftime('%H:%M')}"
                    )
                    st.balloons()
                except Exception as e:
                    st.error(f"Gagal menyimpan: {e}")


# ─────────────────────────────────────────────
# PAGE 2 — VIEW DATA
# ─────────────────────────────────────────────
elif menu == "View Data":
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.title("Riwayat Transaksi")
        st.caption("Lihat, filter, dan kelola semua data transaksi")
    with col_refresh:
        st.write("")
        if st.button("Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    st.divider()

    show_void = st.toggle("Tampilkan transaksi yang sudah di-void", value=False)
    df = load_data(ttl=60, include_void=show_void)

    if df.empty:
        st.info("Belum ada data transaksi. Mulai catat di menu Form Keuangan.")
    else:
        # ── FILTERS ─────────────────────────────
        with st.expander("Filter Data", expanded=True):
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                min_date = df["Tanggal"].min() if pd.notna(df["Tanggal"].min()) else date.today()
                max_date = df["Tanggal"].max() if pd.notna(df["Tanggal"].max()) else date.today()
                date_range = st.date_input(
                    "Rentang Tanggal",
                    value=(min_date, max_date),
                    min_value=min_date,
                    max_value=max_date,
                )
            with fc2:
                jenis_filter = st.multiselect(
                    "Jenis Transaksi",
                    options=["Pemasukan", "Pengeluaran"],
                    default=["Pemasukan", "Pengeluaran"],
                )
            with fc3:
                metode_filter = st.multiselect(
                    "Metode Pembayaran",
                    options=METODE_OPTIONS,
                    default=METODE_OPTIONS,
                )

        # Apply filters
        filtered = df.copy()
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            filtered = filtered[
                (filtered["Tanggal"] >= date_range[0]) & (filtered["Tanggal"] <= date_range[1])
            ]
        if jenis_filter:
            filtered = filtered[filtered["Jenis"].isin(jenis_filter)]
        if metode_filter:
            filtered = filtered[filtered["Metode"].isin(metode_filter)]

        # ── SUMMARY METRICS ──────────────────────
        total_baris       = len(filtered)
        total_pemasukan   = filtered[filtered["Jenis"] == "Pemasukan"]["Nominal"].sum()
        total_pengeluaran = filtered[filtered["Jenis"] == "Pengeluaran"]["Nominal"].sum()
        keuntungan        = total_pemasukan - total_pengeluaran

        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1:
            st.metric("Total Data", f"{total_baris:,} baris")
        with mc2:
            st.metric("Total Pemasukan", format_rupiah(total_pemasukan))
        with mc3:
            st.metric("Total Pengeluaran", format_rupiah(total_pengeluaran))
        with mc4:
            st.metric(
                "Keuntungan Bersih",
                format_rupiah(keuntungan),
                delta=f"+{format_rupiah(abs(keuntungan))}" if keuntungan >= 0 else f"-{format_rupiah(abs(keuntungan))}",
                delta_color="normal" if keuntungan >= 0 else "inverse",
            )

        st.divider()

        # ── TABEL ────────────────────────────────
        display_df = filtered.copy()
        display_df["Nominal"] = display_df["Nominal"].apply(format_rupiah)
        display_df["Tanggal"] = display_df["Tanggal"].apply(format_tanggal)
        display_df = display_df.sort_values(["Tanggal", "Jam"], ascending=False).reset_index(drop=True)

        # Kolom yang ditampilkan — tambahkan Status jika show_void aktif
        cols_to_show = DISPLAY_COLUMNS + (["Status"] if show_void else [])

        st.dataframe(
            display_df[cols_to_show],
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID Transaksi": st.column_config.TextColumn("ID Transaksi", width="medium"),
                "Tanggal":      st.column_config.TextColumn("Tanggal", width="small"),
                "Jam":          st.column_config.TextColumn("Jam", width="small"),
                "Jenis":        st.column_config.TextColumn("Jenis", width="small"),
                "Kategori":     st.column_config.TextColumn("Kategori", width="medium"),
                "Detail":       st.column_config.TextColumn("Detail", width="large"),
                "Qty":          st.column_config.NumberColumn("Qty", width="small"),
                "Nominal":      st.column_config.TextColumn("Nominal", width="medium"),
                "Metode":       st.column_config.TextColumn("Metode", width="small"),
                "Status":       st.column_config.TextColumn("Status", width="small"),
            },
        )

        # ═══════════════════════════════════════════
        # VOID / KOREKSI TRANSAKSI
        # ═══════════════════════════════════════════
        st.divider()
        st.subheader("Void / Koreksi Transaksi")
        st.caption("Batalkan atau perbaiki transaksi yang salah input")

        # Hanya tampilkan transaksi aktif untuk dipilih
        active_df = df[df["Status"] == STATUS_AKTIF].sort_values(
            ["Tanggal", "Jam"], ascending=False
        )

        if active_df.empty:
            st.info("Tidak ada transaksi aktif untuk di-void/koreksi.")
        else:
            # Format pilihan TX agar mudah dibaca
            tx_options = {
                f"{row['ID Transaksi']} | {format_tanggal(row['Tanggal'])} | {row['Jenis']} | {row['Kategori']} | {format_rupiah(row['Nominal'])}": row["ID Transaksi"]
                for _, row in active_df.iterrows()
            }

            selected_label = st.selectbox(
                "Pilih Transaksi",
                options=list(tx_options.keys()),
                index=None,
                placeholder="— Pilih transaksi untuk dikelola —",
            )

            if selected_label:
                selected_tx_id = tx_options[selected_label]
                tx_row = active_df[active_df["ID Transaksi"] == selected_tx_id].iloc[0]

                # Preview transaksi yang dipilih
                with st.container(border=True):
                    pc1, pc2, pc3, pc4, pc5 = st.columns([2, 2, 2, 2, 2])
                    pc1.markdown(f"**Tanggal**\n\n{tx_row['Tanggal']}")
                    pc2.markdown(f"**Jenis**\n\n{tx_row['Jenis']}")
                    pc3.markdown(f"**Kategori**\n\n{tx_row['Kategori']}")
                    pc4.markdown(f"**Nominal**\n\n{format_rupiah(tx_row['Nominal'])}")
                    pc5.markdown(f"**Metode**\n\n{tx_row['Metode']}")
                    st.caption(f"Detail: {tx_row['Detail']}  |  Qty: {tx_row['Qty']}  |  ID: `{selected_tx_id}`")

                col_btn_void, col_btn_edit, col_spacer = st.columns([1, 1, 3])
                with col_btn_void:
                    if st.button("Void (Batalkan)", use_container_width=True):
                        st.session_state.confirm_void_id = selected_tx_id
                        st.session_state.edit_tx_id = None
                with col_btn_edit:
                    if st.button("Koreksi (Edit)", use_container_width=True):
                        st.session_state.edit_tx_id = selected_tx_id
                        st.session_state.confirm_void_id = None

            # ── KONFIRMASI VOID ──────────────────────
            if st.session_state.confirm_void_id:
                void_id = st.session_state.confirm_void_id
                st.warning(
                    f"Yakin ingin membatalkan (void) transaksi {void_id}? "
                    "Data tidak akan dihapus dari sheet, hanya ditandai sebagai Void."
                )
                cv1, cv2, cv3 = st.columns([1, 1, 4])
                with cv1:
                    if st.button("Ya, Void", type="primary", use_container_width=True):
                        with st.spinner("Memproses void..."):
                            if void_transaction(void_id):
                                st.success(f"Transaksi `{void_id}` berhasil di-void.")
                                st.session_state.confirm_void_id = None
                                st.rerun()
                with cv2:
                    if st.button("Batal", use_container_width=True):
                        st.session_state.confirm_void_id = None
                        st.rerun()

            # ── FORM KOREKSI ─────────────────────────
            if st.session_state.edit_tx_id:
                edit_id = st.session_state.edit_tx_id
                edit_row = active_df[active_df["ID Transaksi"] == edit_id]

                if edit_row.empty:
                    st.session_state.edit_tx_id = None
                else:
                    edit_row = edit_row.iloc[0]
                    st.markdown(f"#### Form Koreksi — {edit_id}")

                    # Tentukan jenis & kategori default
                    jenis_default_idx = 0 if edit_row["Jenis"] == "Pemasukan" else 1

                    with st.form("form_koreksi"):
                        ek1, ek2, ek3 = st.columns(3)
                        with ek1:
                            new_jenis = st.selectbox(
                                "Jenis Transaksi",
                                options=JENIS_OPTIONS,
                                index=jenis_default_idx,
                            )
                        with ek2:
                            if new_jenis == "Pemasukan (Penjualan)":
                                kat_options = KATEGORI_PEMASUKAN
                            else:
                                kat_options = KATEGORI_PENGELUARAN
                            kat_default = edit_row["Kategori"] if edit_row["Kategori"] in kat_options else kat_options[0]
                            new_kategori = st.selectbox(
                                "Kategori",
                                options=kat_options,
                                index=kat_options.index(kat_default),
                            )
                        with ek3:
                            metode_default = edit_row["Metode"] if edit_row["Metode"] in METODE_OPTIONS else METODE_OPTIONS[0]
                            new_metode = st.selectbox(
                                "Metode Pembayaran",
                                options=METODE_OPTIONS,
                                index=METODE_OPTIONS.index(metode_default),
                            )

                        new_detail = st.text_input("Detail / Varian Rasa", value=str(edit_row["Detail"]))

                        ek4, ek5 = st.columns([1, 2])
                        with ek4:
                            new_qty = st.number_input("Qty", min_value=1, value=int(edit_row["Qty"]), step=1)
                        with ek5:
                            new_nominal = st.number_input(
                                "Nominal Total (Rp)",
                                min_value=0,
                                value=int(edit_row["Nominal"]),
                                step=1000,
                                format="%d",
                            )

                        col_save, col_cancel = st.columns([1, 1])
                        with col_save:
                            save_koreksi = st.form_submit_button("Simpan Koreksi", use_container_width=True, type="primary")
                        with col_cancel:
                            cancel_koreksi = st.form_submit_button("Batal", use_container_width=True)

                    if save_koreksi:
                        errors = []
                        if not new_detail.strip():
                            errors.append("Detail tidak boleh kosong.")
                        if new_nominal <= 0:
                            errors.append("Nominal harus lebih dari 0.")

                        if errors:
                            for err in errors:
                                st.error(err)
                        else:
                            new_jenis_clean = "Pemasukan" if "Pemasukan" in new_jenis else "Pengeluaran"
                            updated = {
                                "ID Transaksi": edit_id,
                                "Tanggal":      format_tanggal(edit_row["Tanggal"]),
                                "Jam":          str(edit_row["Jam"]),
                                "Jenis":        new_jenis_clean,
                                "Kategori":     new_kategori,
                                "Detail":       new_detail.strip(),
                                "Qty":          new_qty,
                                "Nominal":      new_nominal,
                                "Metode":       new_metode,
                                "Status":       STATUS_AKTIF,
                            }
                            with st.spinner("Menyimpan koreksi..."):
                                if update_transaction(edit_id, updated):
                                    st.success(f"Transaksi {edit_id} berhasil dikoreksi.")
                                    st.session_state.edit_tx_id = None
                                    st.rerun()

                    if cancel_koreksi:
                        st.session_state.edit_tx_id = None
                        st.rerun()


# ─────────────────────────────────────────────
# PAGE 3 — DASHBOARD
# ─────────────────────────────────────────────
elif menu == "Dashboard":
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.title("Dashboard Analitik")
        st.caption("Analisis performa keuangan gerai martabak Anda")
    with col_refresh:
        st.write("")
        if st.button("Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    st.divider()
    df = load_data(ttl=120, include_void=False)  # selalu exclude void di dashboard

    if df.empty:
        st.info("Belum ada data untuk dianalisis. Mulai catat transaksi di menu Form Keuangan.")
    else:
        # ── FILTER PERIODE ────────────────────────
        all_dates = df["Tanggal"].dropna().unique()
        min_date  = df["Tanggal"].min()
        max_date  = df["Tanggal"].max()

        filter_col1, filter_col2 = st.columns([1, 3])
        with filter_col1:
            periode = st.selectbox(
                "Periode",
                options=["Semua", "Hari Ini", "7 Hari Terakhir", "Bulan Ini", "Pilih Tanggal"],
            )
        with filter_col2:
            if periode == "Pilih Tanggal":
                tanggal_filter = st.date_input(
                    "Pilih Tanggal",
                    value=max_date,
                    min_value=min_date,
                    max_value=max_date,
                    label_visibility="collapsed",
                )
            else:
                st.write("")

        # Apply periode filter
        df_filtered = df.copy()
        today = today_wib()
        if periode == "Hari Ini":
            df_filtered = df_filtered[df_filtered["Tanggal"] == today]
        elif periode == "7 Hari Terakhir":
            from datetime import timedelta
            df_filtered = df_filtered[df_filtered["Tanggal"] >= today - timedelta(days=6)]
        elif periode == "Bulan Ini":
            df_filtered = df_filtered[
                (df_filtered["Tanggal"].apply(lambda d: d.month if d else None) == today.month) &
                (df_filtered["Tanggal"].apply(lambda d: d.year if d else None) == today.year)
            ]
        elif periode == "Pilih Tanggal":
            df_filtered = df_filtered[df_filtered["Tanggal"] == tanggal_filter]

        if df_filtered.empty:
            st.info("Tidak ada data untuk periode yang dipilih.")
        else:
            pemasukan_df   = df_filtered[df_filtered["Jenis"] == "Pemasukan"]
            pengeluaran_df = df_filtered[df_filtered["Jenis"] == "Pengeluaran"]

            total_pemasukan   = pemasukan_df["Nominal"].sum()
            total_pengeluaran = pengeluaran_df["Nominal"].sum()
            keuntungan        = total_pemasukan - total_pengeluaran

            # ── METRIC CARDS ─────────────────────────
            mc1, mc2, mc3 = st.columns(3)
            with mc1:
                st.metric("Total Pemasukan", format_rupiah(total_pemasukan))
            with mc2:
                st.metric("Total Pengeluaran", format_rupiah(total_pengeluaran))
            with mc3:
                delta_val = format_rupiah(abs(keuntungan))
                st.metric(
                    "Keuntungan Bersih",
                    format_rupiah(keuntungan),
                    delta=f"+{delta_val}" if keuntungan >= 0 else f"-{delta_val}",
                    delta_color="normal" if keuntungan >= 0 else "inverse",
                )

            st.divider()

            # ── CHART 1: TREN PENJUALAN (Line) ───────
            st.subheader("Tren Penjualan Harian")

            daily = (
                pemasukan_df.groupby("Tanggal")["Nominal"]
                .sum()
                .reset_index()
                .sort_values("Tanggal")
            )
            daily["Tanggal"] = daily["Tanggal"].apply(format_tanggal)

            if not daily.empty and len(daily) > 1:
                fig_line = px.line(
                    daily,
                    x="Tanggal",
                    y="Nominal",
                    markers=True,
                    line_shape="spline",
                    labels={"Nominal": "Omset (Rp)", "Tanggal": "Tanggal"},
                )
                fig_line.update_traces(line=dict(width=2), marker=dict(size=7), fill="tozeroy")
                fig_line.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_line, use_container_width=True)
            elif not daily.empty:
                st.info(f"Data hanya untuk 1 tanggal — total omset: **{format_rupiah(daily['Nominal'].sum())}**")
            else:
                st.info("Belum ada data pemasukan untuk grafik tren.")

            # ── CHART 2 & 3 (side by side) ───────────
            ch1, ch2 = st.columns(2)

            with ch1:
                st.subheader("Distribusi Produk")
                produk = pemasukan_df[pemasukan_df["Kategori"] != "Lain-lain"]
                if not produk.empty:
                    produk_group = produk.groupby("Kategori")["Nominal"].sum().reset_index()
                    fig_pie = px.pie(
                        produk_group,
                        names="Kategori",
                        values="Nominal",
                        hole=0.5,
                    )
                    fig_pie.update_traces(pull=[0.03] * len(produk_group))
                    fig_pie.update_layout(
                        height=360,
                        margin=dict(l=10, r=10, t=10, b=10),
                        legend=dict(orientation="v"),
                    )
                    fig_pie.add_annotation(
                        text="Produk", x=0.5, y=0.5,
                        font=dict(size=13), showarrow=False,
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("Belum ada data penjualan produk martabak.")

            with ch2:
                st.subheader("Metode Pembayaran")
                if not pemasukan_df.empty:
                    metode_group = (
                        pemasukan_df.groupby("Metode")["Nominal"].sum().reset_index()
                        .sort_values("Nominal", ascending=True)
                    )
                    fig_bar = px.bar(
                        metode_group,
                        x="Nominal",
                        y="Metode",
                        orientation="h",
                        text="Nominal",
                        labels={"Nominal": "Total (Rp)", "Metode": ""},
                    )
                    fig_bar.update_traces(
                        texttemplate="Rp %{x:,.0f}",
                        textposition="outside",
                    )
                    fig_bar.update_layout(
                        height=360,
                        margin=dict(l=10, r=80, t=10, b=10),
                        xaxis=dict(showticklabels=False),
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)
                else:
                    st.info("Belum ada data metode pembayaran.")

            # ── RECENT TRANSACTIONS ───────────────────
            st.divider()
            st.subheader("Transaksi Terbaru (10 terakhir)")
            recent = df_filtered.sort_values(["Tanggal", "Jam"], ascending=False).head(10).copy()
            recent["Nominal"] = recent["Nominal"].apply(format_rupiah)
            recent["Tanggal"] = recent["Tanggal"].apply(format_tanggal)
            st.dataframe(
                recent[["Tanggal", "Jam", "Jenis", "Kategori", "Detail", "Nominal", "Metode"]],
                use_container_width=True,
                hide_index=True,
            )
