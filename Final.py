from datetime import datetime
import json
import os
import sqlite3
import calendar
import re
import streamlit as st

# Library tambahan untuk PDF
import fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from PIL import Image as PILImage

# Library RouterOS API
import routeros_api

# Konfigurasi Halaman Streamlit
st.set_page_config(
    page_title="Sistem Manajemen & Rekap RT/RW Net",
    page_icon="🌐",
    layout="wide"
)

# Inisialisasi Database SQLite
def init_db():
    conn = sqlite3.connect("rt_rw_net.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pelanggan (
            id TEXT PRIMARY KEY,
            nama TEXT,
            alias TEXT DEFAULT '',
            no_hp TEXT,
            alamat TEXT,
            paket TEXT,
            iuran REAL,
            perawatan REAL DEFAULT 0,
            admin REAL DEFAULT 0,
            status_bayar TEXT DEFAULT 'Belum Bayar'
        )
    """)
    for col, default in [("alias", "''"), ("perawatan", "0"), ("admin", "0")]:
        try:
            cursor.execute(f"ALTER TABLE pelanggan ADD COLUMN {col} TEXT DEFAULT {default}" if col=="alias" else f"ALTER TABLE pelanggan ADD COLUMN {col} REAL DEFAULT {default}")
        except sqlite3.OperationalError:
            pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transaksi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jenis TEXT,
            kategori TEXT,
            jumlah REAL,
            keterangan TEXT,
            tanggal TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

for fldr in ["database", "hasil_pdf", "hasil_jpg", "laporan"]:
    if not os.path.exists(fldr):
        os.makedirs(fldr)

st.title("🌐 Sistem Manajemen & Rekap Pelanggan RT/RW Net")
st.markdown("---")

# Sidebar untuk Konfigurasi & Navigasi
st.sidebar.header("⚙️ Konfigurasi MikroTik")
pilihan_mk = st.sidebar.selectbox("Pilih Seri MikroTik:", ["MikroTik 1 (A) - Port 3443", "MikroTik 2 (B) - Port 3444"])
if "3443" in pilihan_mk:
    default_host = "remote9.vpnmurahjogja.my.id:3443"
else:
    default_host = "remote9.vpnmurahjogja.my.id:3444"

host_input = st.sidebar.text_input("Host:Port", value=default_host)
user_input = st.sidebar.text_input("Username", value="admin")
pass_input = st.sidebar.text_input("Password", type="password", value="15hf4d4n4Qt4selamanya")

def koneksi_mikrotik():
    try:
        if ":" in host_input:
            HOST, port_str = host_input.split(":", 1)
            PORT = int(port_str)
        else:
            HOST, port_str = host_input, 8728
        
        pool = routeros_api.RouterOsApiPool(
            host=HOST, username=user_input, password=pass_input, port=PORT,
            plaintext_login=True, use_ssl=False, ssl_verify=False, ssl_verify_hostname=False
        )
        return pool, pool.get_api()
    except Exception as e:
        st.sidebar.error(f"Gagal terhubung ke MikroTik: {e}")
        return None, None

menu = st.sidebar.radio("Navigasi Menu", ["Data & Rekap Pelanggan", "Pencatatan Keuangan Kas"])

# --- TAB 1: DATA & REKAP PELANGGAN ---
if menu == "Data & Rekap Pelanggan":
    st.subheader("📋 Data Pelanggan & Rekapitulasi")

    # Tombol Sinkronisasi MikroTik
    if st.sidebar.button("🔄 Sinkronkan Data dari MikroTik"):
        connection, client = koneksi_mikrotik()
        if client:
            try:
                secrets = client.get_resource('/ppp/secret').get()
                conn = sqlite3.connect("rt_rw_net.db")
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM pelanggan WHERE id LIKE 'SPW-%'")
                angka_list = [int(p[0].split("-")[1]) for p in cursor.fetchall() if len(p[0].split("-")) == 2 and p[0].split("-")[1].isdigit()]
                next_num = max(angka_list) + 1 if angka_list else 110

                count_sync = 0
                for sec in secrets:
                    nama = sec.get('name')
                    profile = sec.get('profile', 'default')
                    cursor.execute("SELECT id FROM pelanggan WHERE nama = ?", (nama,))
                    if not cursor.fetchone():
                        new_id = f"SPW-{next_num}"
                        next_num += 1
                        alias_format = nama.replace("_", " ").title()
                        cursor.execute("INSERT OR IGNORE INTO pelanggan VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                       (new_id, nama, alias_format, "-", "Kecer, Dasuk, Sumenep", profile, 50000, 0, 0, "Belum Bayar"))
                        count_sync += 1
                conn.commit()
                conn.close()
                st.success(f"Berhasil menyinkronkan {count_sync} pelanggan baru!")
                st.rerun()
            except Exception as e:
                st.error(f"Error sinkronisasi: {e}")
            finally:
                connection.disconnect()

    # Tampilkan Ringkasan
    conn = sqlite3.connect("rt_rw_net.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, nama, alias, no_hp, alamat, paket, iuran, perawatan, admin, status_bayar FROM pelanggan ORDER BY nama ASC")
    rows = cursor.fetchall()
    conn.close()

    total_pelanggan = len(rows)
    total_terkumpul = sum([(r[6]+r[7]+r[8]) for r in rows if r[9] == "Sudah Bayar"])
    total_potensi = sum([(r[6]+r[7]+r[8]) for r in rows])

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Pelanggan", f"{total_pelanggan} Orang")
    col2.metric("Sudah Dibayar", f"Rp {total_terkumpul:,.0f}".replace(",", "."))
    col3.metric("Potensi Iuran", f"Rp {total_potensi:,.0f}".replace(",", "."))

    st.markdown("---")

    # Pencarian & Tabel Pelanggan
    cari = st.text_input("🔍 Cari Pelanggan (Nama/ID/Alamat/No HP):")
    
    filtered_rows = []
    for r in rows:
        if not cari or any(cari.lower() in str(val).lower() for val in r):
            filtered_rows.append(r)

    for idx, r in enumerate(filtered_rows, 1):
        pel_id, nama, alias, no_hp, alamat, paket, iuran, perawatan, admin, status_bayar = r
        sub_total = iuran + perawatan + admin
        
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([1, 3, 2, 2, 2])
            c1.write(f"**{idx}**")
            c2.write(f"**{alias if alias else nama}**\n\n`ID: {pel_id}` | HP: {no_hp}")
            c3.write(f"Paket: **{paket}**\n\nAlamat: {alamat}")
            c4.write(f"Tagihan: **Rp {sub_total:,.0f}**\n\nStatus: **{status_bayar}**")
            
            with c5:
                if status_bayar != "Sudah Bayar":
                    if st.button("Ubah Sudah Bayar", key=f"bayar_{pel_id}"):
                        conn = sqlite3.connect("rt_rw_net.db")
                        cursor = conn.cursor()
                        cursor.execute("UPDATE pelanggan SET status_bayar = 'Sudah Bayar' WHERE id = ?", (pel_id,))
                        cursor.execute("INSERT INTO transaksi (jenis, kategori, jumlah, keterangan, tanggal) VALUES (?, ?, ?, ?, ?)",
                                       ("Pemasukan", "Iuran Bulanan Pelanggan", sub_total, f"Iuran dari: {nama}", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        conn.commit()
                        conn.close()
                        st.success("Status diperbarui!")
                        st.rerun()
                else:
                    if st.button("Ubah Belum Bayar", key=f" belum_{pel_id}"):
                        conn = sqlite3.connect("rt_rw_net.db")
                        cursor = conn.cursor()
                        cursor.execute("UPDATE pelanggan SET status_bayar = 'Belum Bayar' WHERE id = ?", (pel_id,))
                        conn.commit()
                        conn.close()
                        st.warning("Status diubah ke Belum Bayar")
                        st.rerun()

                # Tombol Generate Kuitansi PDF
                if status_bayar == "Sudah Bayar":
                    if st.button("📄 Buat Kuitansi PDF", key=f"pdf_{pel_id}"):
                        # Logika pembuatan PDF ringkas
                        nama_pdf = os.path.join("hasil_pdf", f"Kuitansi_{pel_id}.pdf")
                        doc = SimpleDocTemplate(nama_pdf, pagesize=letter)
                        story = [Paragraph(f"<b>Kuitansi Pembayaran RT/RW Net</b><br/>Pelanggan: {nama} [ID: {pel_id}]<br/>Total: Rp {sub_total:,.0f}", getSampleStyleSheet()['Normal'])]
                        doc.build(story)
                        st.success(f"Kuitansi tersimpan di {nama_pdf}")
            st.markdown("---")

# --- TAB 2: PENCATATAN KEUANGAN KAS ---
elif menu == "Data Keuangan Kas":
    st.subheader("💰 Pencatatan Keuangan Kas RT/RW Net")
    
    with st.form("form_keuangan"):
        j_transaksi = st.selectbox("Jenis Transaksi", ["Pemasukan", "Pengeluaran"])
        k_transaksi = st.selectbox("Kategori", ["Iuran Bulanan Pelanggan", "Penjualan Voucher Hotspot", "Bayar Bandwidth / Upstream", "Listrik & Tempat", "Maintenance / Alat Rusak", "Lain-lain"])
        jml_transaksi = st.number_input("Jumlah (Rp)", min_value=0.0, step=1000.0)
        ket_transaksi = st.text_input("Keterangan")
        submitted = st.form_submit_button("Simpan Transaksi")
        
        if submitted:
            conn = sqlite3.connect("rt_rw_net.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO transaksi (jenis, kategori, jumlah, keterangan, tanggal) VALUES (?, ?, ?, ?, ?)",
                           (j_transaksi, k_transaksi, jml_transaksi, ket_transaksi, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()
            st.success("Transaksi berhasil dicatat!")

    st.markdown("### Riwayat Transaksi")
    conn = sqlite3.connect("rt_rw_net.db")
    cursor = conn.cursor()
    cursor.execute("SELECT jenis, kategori, jumlah, keterangan, tanggal FROM transaksi ORDER BY id DESC")
    trans_rows = cursor.fetchall()
    conn.close()

    for tr in trans_rows:
        jenis, kat, jml, ket, tgl = tr
        color = "green" if jenis == "Pemasukan" else "red"
        st.markdown(f"- **{tgl}** | :{color}[{jenis}] | **{kat}** | Rp {jml:,.0f} | *{ket}*")