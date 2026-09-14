import streamlit as st
import pandas as pd
import sqlite3
import os
import json
from datetime import datetime
import calendar
import re
import routeros_api

# 1. Konfigurasi Halaman Web
st.set_page_config(
    page_title="Sistem Manajemen RT/RW Net",
    page_icon="📶",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Inisialisasi Database SQLite
def init_db():
    conn = sqlite3.connect("rt_rw_net.db")
    cursor = conn.cursor()
    cursor.execute('''
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
    ''')
    try:
        cursor.execute("ALTER TABLE pelanggan ADD COLUMN alias TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE pelanggan ADD COLUMN perawatan REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE pelanggan ADD COLUMN admin REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transaksi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jenis TEXT,
            kategori TEXT,
            jumlah REAL,
            keterangan TEXT,
            tanggal TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Buat folder penyimpanan jika belum ada
for fldr in ["database", "hasil_pdf", "hasil_jpg", "laporan"]:
    if not os.path.exists(fldr):
        os.makedirs(fldr)

# 3. Sidebar Konfigurasi MikroTik & Navigasi
st.sidebar.title("⚙️ Konfigurasi MikroTik")
seri_pilihan = st.sidebar.selectbox("Pilih Seri MikroTik", ["Seri A (MikroTik 1)", "Seri B (MikroTik 2)"])

if "Seri A" in seri_pilihan:
    default_host = "remote9.vpnmurahjogja.my.id:3443"
else:
    default_host = "remote9.vpnmurahjogja.my.id:3444"

host_input = st.sidebar.text_input("Host:Port", value=default_host)
user_input = st.sidebar.text_input("Username", value="admin")
pass_input = st.sidebar.text_input("Password", value="15hf4d4n4Qt4selamanya", type="password")

st.sidebar.markdown("---")
menu = st.sidebar.radio("📂 Menu Navigasi", ["Data & Rekap Pelanggan", "Pencatatan Keuangan Kas", "Sinkronisasi MikroTik"])

# Fungsi Koneksi MikroTik
def koneksi_mikrotik():
    connection = None
    try:
        if not host_input:
            return None, None
        if ":" in host_input:
            HOST, port_str = host_input.split(":", 1)
            PORT = int(port_str)
        else:
            HOST = host_input
            PORT = 8728

        connection = routeros_api.RouterOsApiPool(
            host=HOST,
            username=user_input.strip(),
            password=pass_input,
            port=PORT,
            plaintext_login=True,
            use_ssl=False,
            ssl_verify=False,
            ssl_verify_hostname=False
        )
        client = connection.get_api()
        return connection, client
    except Exception as e:
        if connection:
            try:
                connection.disconnect()
            except Exception:
                pass
        return None, None

# Main Title
st.title("📶 Sistem Manajemen & Rekap Pelanggan RT/RW Net")

# 4. Halaman Data & Rekap Pelanggan
if menu == "Data & Rekap Pelanggan":
    st.subheader("📋 Rekapitulasi Data Pelanggan")
    
    # Ambil data dari database
    conn = sqlite3.connect("rt_rw_net.db")
    df_pelanggan = pd.read_sql_query("SELECT * FROM pelanggan ORDER BY nama ASC", conn)
    conn.close()

    # Hitung ringkasan
    total_pelanggan = len(df_pelanggan)
    potensi_iuran = (df_pelanggan['iuran'] + df_pelanggan['perawatan'] + df_pelanggan['admin']).sum() if total_pelanggan > 0 else 0
    
    lunas_df = df_pelanggan[df_pelanggan['status_bayar'] == 'Sudah Bayar']
    terkumpul = (lunas_df['iuran'] + lunas_df['perawatan'] + lunas_df['admin']).sum() if len(lunas_df) > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Pelanggan", f"{total_pelanggan} Orang")
    col2.metric("Sudah Dibayar", f"Rp {terkumpul:,.0f}".replace(",", "."))
    col3.metric("Potensi Iuran", f"Rp {potensi_iuran:,.0f}".replace(",", "."))

    st.markdown("---")

    # Tombol Aksi Cepat & Pencarian
    c_cari, c_btn1, c_btn2 = st.columns([2, 1, 1])
    pencarian = c_cari.text_input("🔍 Cari Pelanggan (Nama/ID/Alamat/No HP)")
    
    if pencarian:
        mask = df_pelanggan.apply(lambda row: row.astype(str).str.contains(pencarian, case=False).any(), axis=1)
        df_tampil = df_pelanggan[mask]
    else:
        df_tampil = df_pelanggan

    # Tampilkan Tabel
    if not df_tampil.empty:
        # Format kolom total tagihan
        df_tampil['Total Tagihan'] = df_tampil['iuran'] + df_tampil['perawatan'] + df_tampil['admin']
        
        st.dataframe(
            df_tampil[['id', 'nama', 'alias', 'no_hp', 'alamat', 'paket', 'Total Tagihan', 'status_bayar']],
            column_config={
                "id": "ID Pelanggan",
                "nama": "Nama Secret",
                "alias": "Nama Alias",
                "no_hp": "No HP/WA",
                "alamat": "Alamat",
                "paket": "Paket",
                "Total Tagihan": st.column_config.NumberColumn("Total Tagihan (Rp)", format="Rp %d"),
                "status_bayar": "Status Pembayaran"
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Belum ada data pelanggan tersimpan.")

    # Form Tambah Pelanggan Baru di bawah
    with st.expander("➕ Tambah Pelanggan Baru"):
        with st.form("form_tambah_pelanggan"):
            c1, c2 = st.columns(2)
            
            # Generate ID otomatis
            conn = sqlite3.connect("rt_rw_net.db")
            cur = conn.cursor()
            cur.execute("SELECT id FROM pelanggan WHERE id LIKE 'SPW-%'")
            rows_id = cur.fetchall()
            conn.close()
            angka_list = [int(p[0].split("-")[1]) for p in rows_id if len(p[0].split("-")) == 2 and p[0].split("-")[1].isdigit()]
            next_id = f"SPW-{max(angka_list) + 1 if angka_list else 110}"

            f_id = c1.text_input("ID Pelanggan", value=next_id)
            f_nama = c1.text_input("Nama Secret (MikroTik)")
            f_alias = c1.text_input("Nama Alias (Panggilan)")
            f_hp = c1.text_input("No HP / WhatsApp", value="-")
            f_alamat = c2.text_input("Alamat Lengkap", value="Kecer, Dasuk, Sumenep")
            f_paket = c2.text_input("Paket Internet", value="profile-7mbps")
            f_iuran = c2.number_input("Iuran Internet (Rp)", value=50000, step=5000)
            f_perawatan = c2.number_input("Biaya Perawatan (Rp)", value=0, step=1000)
            f_admin = c2.number_input("Biaya Admin (Rp)", value=0, step=1000)
            f_status = c2.selectbox("Status Bayar", ["Belum Bayar", "Sudah Bayar"])

            submit_add = st.form_submit_button("Simpan Pelanggan")
            if submit_add:
                if not f_nama:
                    st.error("Nama Secret tidak boleh kosong!")
                else:
                    alias_final = f_alias.title() if f_alias else f_nama.title()
                    conn = sqlite3.connect("rt_rw_net.db")
                    cur = conn.cursor()
                    try:
                        cur.execute("INSERT INTO pelanggan VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                    (f_id, f_nama, alias_final, f_hp, f_alamat, f_paket, f_iuran, f_perawatan, f_admin, f_status))
                        if f_status == "Sudah Bayar":
                            total_tagihan = f_iuran + f_perawatan + f_admin
                            cur.execute("INSERT INTO transaksi (jenis, kategori, jumlah, keterangan, tanggal) VALUES (?, ?, ?, ?, ?)",
                                        ("Pemasukan", "Iuran Bulanan Pelanggan", total_tagihan, f"Iuran dari: {f_nama}", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        conn.commit()
                        conn.close()
                        st.success("Data pelanggan berhasil disimpan!")
                        st.rerun()
                    except Exception as e:
                        conn.close()
                        st.error(f"Gagal menyimpan: {e}")

# 5. Halaman Pencatatan Keuangan Kas
elif menu == "Pencatatan Keuangan Kas":
    st.subheader("💰 Pencatatan Kas RT/RW Net")
    
    with st.form("form_keuangan"):
        c1, c2 = st.columns(2)
        j_transaksi = c1.radio("Jenis Transaksi", ["Pemasukan", "Pengeluaran"])
        kategori_pilihan = ["Iuran Bulanan Pelanggan", "Penjualan Voucher Hotspot", "Bayar Bandwidth / Upstream", "Listrik & Tempat", "Maintenance / Alat Rusak", "Lain-lain"]
        k_transaksi = c1.selectbox("Kategori", kategori_pilihan)
        jml_transaksi = c2.number_input("Jumlah (Rp)", value=50000, step=10000)
        ket_transaksi = c2.text_input("Keterangan")
        
        btn_kas = st.form_submit_button("Simpan Transaksi Kas")
        if btn_kas:
            conn = sqlite3.connect("rt_rw_net.db")
            cur = conn.cursor()
            cur.execute("INSERT INTO transaksi (jenis, kategori, jumlah, keterangan, tanggal) VALUES (?, ?, ?, ?, ?)",
                        (j_transaksi, k_transaksi, jml_transaksi, ket_transaksi, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()
            st.success("Transaksi kas berhasil disimpan!")
            st.rerun()

    st.markdown("### Riwayat Transaksi Kas")
    conn = sqlite3.connect("rt_rw_net.db")
    df_keu = pd.read_sql_query("SELECT * FROM transaksi ORDER BY id DESC", conn)
    conn.close()

    if not df_keu.empty:
        st.dataframe(df_keu, use_container_width=True, hide_index=True)
    else:
        st.info("Belum ada catatan transaksi.")

# 6. Halaman Sinkronisasi MikroTik
elif menu == "Sinkronisasi MikroTik":
    st.subheader("🔄 Sinkronisasi Data Pelanggan dari MikroTik")
    st.write("Fitur ini akan menarik data PPP Secrets dari router MikroTik yang terhubung dan menambahkannya ke database lokal secara otomatis jika belum ada.")

    if st.button("Mulai Sinkronisasi Sekarang", type="primary"):
        with st.spinner("Menghubungkan ke MikroTik..."):
            connection, client = koneksi_mikrotik()
            if not client:
                st.error("Gagal terhubung ke MikroTik. Pastikan Host, Username, dan Password benar serta port API aktif.")
            else:
                try:
                    list_secret = client.get_resource('/ppp/secret')
                    secrets = list_secret.get()

                    conn = sqlite3.connect("rt_rw_net.db")
                    cursor = conn.cursor()

                    cursor.execute("SELECT id FROM pelanggan WHERE id LIKE 'SPW-%'")
                    rows_id = cursor.fetchall()
                    angka_list = [int(p[0].split("-")[1]) for p in rows_id if len(p[0].split("-")) == 2 and p[0].split("-")[1].isdigit()]
                    next_num = max(angka_list) + 1 if angka_list else 110

                    count_sync = 0
                    for sec in secrets:
                        nama = sec.get('name')
                        profile = sec.get('profile', 'default')
                        
                        cursor.execute("SELECT id FROM pelanggan WHERE nama = ?", (nama,))
                        existing = cursor.fetchone()

                        if not existing:
                            new_id = f"SPW-{next_num}"
                            next_num += 1
                            alias_format = nama.replace("_", " ").title()
                            cursor.execute('''
                                INSERT OR IGNORE INTO pelanggan (id, nama, alias, no_hp, alamat, paket, iuran, status_bayar)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (new_id, nama, alias_format, "-", "Kecer, Dasuk, Sumenep", profile, 50000, "Belum Bayar"))
                            count_sync += 1

                    conn.commit()
                    conn.close()
                    st.success(f"Berhasil menyinkronkan {count_sync} data pelanggan baru dari MikroTik!")
                except Exception as e:
                    st.error(f"Terjadi kesalahan saat sinkronisasi: {e}")
                finally:
                    if connection:
                        try:
                            connection.disconnect()
                        except Exception:
                            pass
