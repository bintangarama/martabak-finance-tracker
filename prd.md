# Product Requirement Document (PRD)
## Project Name: Martabak Finance Tracker (MFT)
**Version:** 1.0  
**Target Platform:** AntiGravity (Streamlit-based App)  
**Database Backend:** Google Sheets  

---

## 1. Executive Summary & Objective
Aplikasi **Martabak Finance Tracker (MFT)** adalah sebuah sistem pencatatan keuangan berbasis web yang dirancang khusus untuk UMKM Martabak. Tujuannya adalah mempermudah kasir/pemilik dalam mencatat transaksi harian secara cepat melalui HP/perangkat web, melihat riwayat data, dan menganalisis performa penjualan melalui dashboard visual. Seluruh data akan disimpan secara terpusat dan *real-time* di Google Sheets.

---

## 2. User Personas
* **Kasir / Operasional Outlet:** Membutuhkan antarmuka yang simpel, tombol yang besar (ramah perangkat seluler), dan proses input yang cepat saat melayani pelanggan.
* **Pemilik UMKM (Owner):** Membutuhkan visualisasi tren penjualan, laporan keuntungan bersih, dan kemampuan untuk meninjau ulang data transaksi mentah.

---

## 3. Core Features & Scope

Aplikasi ini dibagi menjadi 3 menu utama navigasi (Sidebar):
1.  **Form Keuangan (Input Transaksi)**
2.  **View Data (Tabel & Riwayat)**
3.  **Dashboard (Analisis & Grafik)**

### 3.1. Form Keuangan (Input Transaksi)
Fitur untuk mencatat setiap transaksi yang terjadi di gerai martabak.

* **Komponen Input:**
    * `Tanggal`: Input penanggalan (default ke tanggal hari ini).
    * `Jenis Transaksi`: Pilihan antara `Pemasukan (Penjualan)` atau `Pengeluaran (Operasional/Bahan Baku)`.
    * `Kategori Martabak` *(Hanya muncul jika Pemasukan)*: Pilihan dropdown: `Martabak Manis`, `Martabak Telor`, `Tipker (Tipis Kering)`, `Lain-lain`.
    * `Detail / Varian Rasa`: Input teks bebas (contoh: *Cokelat Keju Spesial*, *Telor 3 Bebek*, *Beli Terigu 5kg*).
    * `Jumlah (Qty)`: Input angka (default = 1).
    * `Nominal Total (Rp)`: Input angka rupiah (contoh: 45000).
    * `Metode Pembayaran`: Pilihan dropdown: `Tunai`, `QRIS / Transfer`, `Debit`.
* **Sistem Validasi & Logika:**
    * Semua field wajib diisi sebelum data dikirim.
    * Tombol "Simpan Transaksi" akan memicu fungsi *append* data ke baris paling bawah di Google Sheets secara *real-time*.
    * Menampilkan pesan sukses (`st.success`) setelah data berhasil masuk.

### 3.2. View Data (Riwayat & Manajemen)
Fitur untuk melihat, menyaring, dan memantau data yang sudah tersimpan di Google Sheets.

* **Fitur Utama:**
    * `Tampilan Tabel`: Menampilkan seluruh baris data transaksi dari Google Sheets menggunakan dataframe interaktif.
    * `Filter Tanggal & Kategori`: Memungkinkan pengguna menyaring data berdasarkan rentang tanggal atau jenis transaksi (Pemasukan/Pengeluaran).
    * `Ringkasan Singkat (Metrics)`: Di atas tabel menampilkan total baris data yang lolos filter.
    * `Tombol Refresh`: Memaksa aplikasi mengambil data paling segar dari Google Sheets (menonaktifkan cache sementara).

### 3.3. Dashboard (Visualisasi & Analisis)
Fitur analitik bagi pemilik untuk memantau kesehatan keuangan bisnis Martabak.

* **Komponen Visual (Metrics Box):**
    * **Total Pemasukan (Rp):** Akumulasi seluruh transaksi masuk.
    * **Total Pengeluaran (Rp):** Akumulasi seluruh pengeluaran bahan baku & operasional.
    * **Keuntungan Bersih (Rp):** Selisih antara Pemasukan dan Pengeluaran (dengan indikator warna hijau jika surplus, merah jika minus).
* **Komponen Grafik (Charts):**
    * *Grafik Tren Penjualan (Line Chart):* Menampilkan fluktuasi omset harian/mingguan.
    * *Grafik Distribusi Produk (Pie/Donut Chart):* Menampilkan persentase jenis martabak yang paling laris (Manis vs Telor vs Tipker).
    * *Grafik Metode Pembayaran (Bar Chart):* Mengetahui preferensi pelanggan (Tunai vs QRIS).

---

## 4. Technical Stack & Integrations
* **Framework:** Streamlit (Python) - dikonfigurasi via platform kode generator AntiGravity.
* **Integrasi Database:** `streamlit-gsheets` (GSheetsConnection) memanfaatkan Service Account (.json token) atau Streamlit Secrets.
* **Data Manipulation:** `pandas` untuk agregasi data dan pengelolaan DataFrame.
* **Visualisasi:** `plotly` atau internal `st.bar_chart` / `st.line_chart`.

---

## 5. Struktur Data Google Sheets (Skema Kolom)
Aplikasi akan menulis data ke dalam satu lembar kerja (Worksheet) bernama `Transaksi` dengan struktur kolom sebagai berikut:

| ID Transaksi | Tanggal | Jenis | Kategori | Detail | Qty | Nominal | Metode |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| TX-001 | 2026-06-12 | Pemasukan | Martabak Manis | Cokelat Keju | 1 | 35000 | QRIS |
| TX-002 | 2026-06-12 | Pengeluaran | Lain-lain | Beli Telor 2 Kg | 1 | 56000 | Tunai |

---

## 6. Non-Functional Requirements
* **Mobile-Friendly:** Layout form wajib responsif dan mudah ditekan pada layar smartphone berukuran kecil (karena kasir martabak sering input lewat HP).
* **Low Latency Connection:** Pengambilan data dari Google Sheets harus menggunakan optimasi cache (`ttl`) yang seimbang agar aplikasi tidak lambat saat dibuka, namun tetap akurat.
* **User Interface:** Desain bernuansa hangat (kombinasi warna kuning keemasan/terracotta/cokelat) yang mencerminkan branding produk Martabak yang lezat dan premium.
