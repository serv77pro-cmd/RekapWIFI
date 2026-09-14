from datetime import datetime
import json
import os
import sqlite3
import calendar
import re
import streamlit as st

# Library tambahan untuk PDF & Gambar
import fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
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
            HOST, PORT = host_input, 8728
        
        pool = routeros_api.RouterOsApiPool(
            host=HOST, username=user_input, password=pass_input, port=PORT,
            plaintext_login=True, use_ssl=False, ssl_verify=False, ssl_verify_hostname=False
        )
        return pool, pool.get_api()
    except Exception as e:
        st.sidebar.error(f"Gagal terhubung ke MikroTik: {e}")
        return None, None

menu = st.sidebar.radio("Navigasi Menu", ["Data & Rekap Pelanggan", "Data Keuangan Kas"])

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
                                       (new_id, nama, alias_format, "-", "Kecer, Dasuk, Sumenep", profile, 50000, 5000, 2000, "Belum Bayar"))
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
        iuran_pokok = float(iuran or 50000)
        biaya_perawatan = float(perawatan or 0)
        biaya_admin = float(admin or 0)
        sub_total = iuran_pokok + biaya_perawatan + biaya_admin
        
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
                    if st.button("Ubah Belum Bayar", key=f"belum_{pel_id}"):
                        conn = sqlite3.connect("rt_rw_net.db")
                        cursor = conn.cursor()
                        cursor.execute("UPDATE pelanggan SET status_bayar = 'Belum Bayar' WHERE id = ?", (pel_id,))
                        conn.commit()
                        conn.close()
                        st.warning("Status diubah ke Belum Bayar")
                        st.rerun()

                # Tombol Generate Kuitansi PDF Lengkap
                if status_bayar == "Sudah Bayar":
                    if st.button("📄 Buat Kuitansi PDF", key=f"pdf_{pel_id}"):
                        try:
                            sekarang = datetime.now()
                            tahun = sekarang.year
                            bulan_angka = sekarang.month
                            hari_terakhir = calendar.monthrange(tahun, bulan_angka)[1]

                            bulan_indo = {
                                1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 5: "Mei", 6: "Juni",
                                7: "Juli", 8: "Agustus", 9: "September", 10: "Oktober", 11: "November", 12: "Desember"
                            }
                            nama_bulan = bulan_indo[bulan_angka]

                            format_tgl_cetak = sekarang.strftime(f"%d {nama_bulan} %Y")
                            format_periode = f"{nama_bulan} {tahun}"
                            format_no_kuitansi = sekarang.strftime(f"SPW-%Y%m-0892")
                            format_jatuh_tempo = f"Mulai 1 Sampai 11 {nama_bulan} {tahun}"

                            nama_bersih_file = re.sub(r'[^a-zA-Z0-9]', '_', nama)
                            nama_pdf = os.path.join("hasil_pdf", f"Kuitansi_{pel_id}_{nama_bersih_file}.pdf")
                            nama_jpg = os.path.join("hasil_jpg", f"Kuitansi_{pel_id}_{nama_bersih_file}.jpg")

                            file_bg_asli = "bg_50rb.jpg"
                            file_bg_watermark = os.path.join("database", "bg_50rb_watermark.png")
                            
                            if not os.path.exists(file_bg_watermark) and os.path.exists(file_bg_asli):
                                try:
                                    img = PILImage.open(file_bg_asli).convert("RGBA")
                                    new_data = [(item[0], item[1], item[2], int(item[3] * 0.5)) for item in img.getdata()]
                                    img.putdata(new_data)
                                    img.save(file_bg_watermark, "PNG")
                                except Exception:
                                    pass

                            def background_canvas(canvas, doc):
                                canvas.saveState()
                                target_bg = file_bg_watermark if os.path.exists(file_bg_watermark) else (file_bg_asli if os.path.exists(file_bg_asli) else "")
                                if target_bg and os.path.exists(target_bg):
                                    canvas.drawImage(target_bg, 0, 0, width=612, height=792, preserveAspectRatio=False, mask='auto')
                                canvas.restoreState()

                            story = []
                            title_style = ParagraphStyle('Title', fontName='Helvetica-Bold', fontSize=22, textColor=colors.HexColor('#1E3A8A'), leading=26)
                            sub_style = ParagraphStyle('Sub', fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#475569'), leading=13)
                            kuitansi_style = ParagraphStyle('Kuitansi', fontName='Helvetica-Bold', fontSize=16, textColor=colors.HexColor('#0F172A'), alignment=1, spaceAfter=4)
                            text_style = ParagraphStyle('Text', fontName='Helvetica', fontSize=10, leading=14, textColor=colors.HexColor('#334155'))
                            
                            story.append(Paragraph("<b>ServPro WIFI</b>", title_style))
                            story.append(Paragraph("<b>Prongpong, Kecer, Dasuk, Sumenep</b>", sub_style))
                            story.append(Paragraph("<b>Jl. K.H. Khatib Bangil No. 125 | No HP/WA Admin: 0818-0322-3334</b>", sub_style))
                            story.append(Paragraph("<b>Pembayaran Via Transfer: BCA 1498-6302-0125-0005 (a/n ServPro) | DANA : 0838-8855-899</b>", sub_style))
                            story.append(Spacer(1, 6))
                            story.append(Table([[""]], colWidths=[552], rowHeights=[3], style=[('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#1E3A8A'))]))
                            story.append(Spacer(1, 10))
                            
                            story.append(Paragraph("KUITANSI PEMBAYARAN", kuitansi_style))
                            story.append(Paragraph(f"<b>No:</b> {format_no_kuitansi}", ParagraphStyle('No', fontName='Helvetica', fontSize=10, alignment=1, textColor=colors.HexColor('#475569'))))
                            story.append(Spacer(1, 12))
                            
                            if alias:
                                p_info = f"<b>PENGGUNA LAYANAN:</b><br/>Nama Asli/Alias: <b>{alias}</b><br/>Secret ID: <b>{nama} [ID:{pel_id}]</b><br/>No HP / WA: {no_hp}<br/>Alamat: {alamat}<br/>Kode Pos 69454"
                            else:
                                p_info = f"<b>PENGGUNA LAYANAN: <b>{nama}</b></b> (ID: {pel_id})<br/>No HP / WA: {no_hp}<br/>Alamat: {alamat}<br/>Kode Pos 69454"

                            t_info = f"<b>DETAIL TAGIHAN:</b><br/>Tanggal Cetak: {format_tgl_cetak}<br/>Periode Layanan: {format_periode}<br/>Jatuh Tempo: <font color='#EF4444'><b>{format_jatuh_tempo}</b></font><br/>Metode Bayar: Transfer / Tunai"
                            t_blok = Table([[Paragraph(p_info, text_style), Paragraph(t_info, text_style)]], colWidths=[276, 276])
                            t_blok.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
                            story.append(t_blok)
                            story.append(Spacer(1, 12))
                            
                            str_iuran = f"Rp {iuran_pokok:,.0f}".replace(",", ".")
                            str_perawatan = f"Rp {biaya_perawatan:,.0f}".replace(",", ".")
                            str_admin = f"Rp {biaya_admin:,.0f}".replace(",", ".")
                            str_total = f"Rp {sub_total:,.0f}".replace(",", ".")
                            
                            data_biaya = [
                                ["No", "Deskripsi Layanan", "Tarif / Biaya", "Total"],
                                ["1", Paragraph(f"<b>Paket {paket}</b><br/><font color='#64748B'>Akses internet unlimited tanpa FUP (01-{hari_terakhir} {nama_bulan} {tahun})</font>", text_style), str_iuran, str_iuran],
                                ["2", Paragraph("<b>Biaya Perawatan Jaringan</b><br/><font color='#64748B'>Maintenance perangkat & kabel optik bulanan</font>", text_style), str_perawatan, str_perawatan],
                                ["3", Paragraph("<b>Biaya Administrasi Sistem</b><br/><font color='#64748B'>Biaya layanan manajemen & server aplikasi</font>", text_style), str_admin, str_admin],
                                ["", "", "Total Bayar", str_total]
                            ]
                            
                            t_biaya = Table(data_biaya, colWidths=[25, 297, 115, 115])
                            t_biaya.setStyle(TableStyle([
                                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
                                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                                ('FONTSIZE', (0,0), (-1,0), 9.5),
                                ('ALIGN', (0,0), (0,-1), 'CENTER'),
                                ('ALIGN', (2,0), (-1,-1), 'RIGHT'),
                                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                                ('TOPPADDING', (0,0), (-1,-1), 5),
                                ('GRID', (0,0), (-1,3), 0.5, colors.HexColor('#CBD5E1')),
                                ('LINEBELOW', (2,4), (3,4), 0.5, colors.HexColor('#E2E8F0')),
                                ('FONTNAME', (2,4), (3,4), 'Helvetica-Bold'),
                                ('TEXTCOLOR', (2,4), (3,4), colors.HexColor('#1E3A8A')),
                                ('BACKGROUND', (0,1), (-1,-1), colors.Color(1, 1, 1, alpha=0.95))
                            ]))
                            story.append(t_biaya)
                            story.append(Spacer(1, 12))
                            
                            catatan = (
                                "<b>Catatan Penting:</b><br/><font color='#64748B'>"
                                "1. Simpan kuitansi ini sebagai bukti pembayaran sah.<br/>"
                                "2. Hubungi admin kami via WhatsApp dengan menyertakan ID Pelanggan.<br/><br/>"
                                "<b>Kontak Admin & CS:</b><br/>• WhatsApp: +62 818-0322-3334</font>"
                            )
                            
                            t_status = Table([[
                                Paragraph(catatan, ParagraphStyle('Catatan', fontName='Helvetica', fontSize=8.5, leading=12, textColor=colors.HexColor('#334155'))), 
                                Paragraph("<b>LUNAS / PAID</b>", ParagraphStyle('Lunas', fontName='Helvetica-Bold', fontSize=14, textColor=colors.HexColor('#15803D'), alignment=1))
                            ]], colWidths=[362, 190])
                            
                            t_status.setStyle(TableStyle([
                                ('BACKGROUND', (0,0), (0,0), colors.Color(1, 1, 1, alpha=0.95)),
                                ('BACKGROUND', (1,0), (1,0), colors.HexColor('#DCFCE7')),
                                ('ALIGN', (1,0), (1,0), 'CENTER'),
                                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                                ('BOX', (1,0), (1,0), 1.5, colors.HexColor('#15803D')),
                                ('TOPPADDING', (1,0), (1,0), 10),
                                ('BOTTOMPADDING', (1,0), (1,0), 10),
                            ]))
                            story.append(t_status)

                            tinggi_total_konten = sum([item.wrap(532, 792)[1] for item in story])
                            tinggi_halaman_tersedia = 792 - 80
                            sisa_ruang = max(0, tinggi_halaman_tersedia - tinggi_total_konten)
                            margin_otomatis = sisa_ruang / 2.0

                            doc = SimpleDocTemplate(
                                nama_pdf, pagesize=letter, 
                                rightMargin=40, leftMargin=40, 
                                topMargin=margin_otomatis, bottomMargin=margin_otomatis
                            )
                            doc.build(story, onFirstPage=background_canvas, onLaterPages=background_canvas)

                            # Konversi halaman PDF ke JPG via PyMuPDF (fitz)
                            pdf_document = fitz.open(nama_pdf)
                            page = pdf_document[0]
                            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
                            pix.save(nama_jpg)
                            pdf_document.close()

                            st.success(f"Kuitansi berhasil dibuat!")
                            with open(nama_pdf, "rb") as pdf_file:
                                st.download_button(
                                    label="📥 Unduh File PDF Kuitansi",
                                    data=pdf_file,
                                    file_name=os.path.basename(nama_pdf),
                                    mime="application/pdf",
                                    key=f"dl_pdf_{pel_id}"
                                />
                            if os.path.exists(nama_jpg):
                                st.image(nama_jpg, caption=f"Pratinjau Kuitansi - {nama}", use_container_width=True)

                        except Exception as e:
                            st.error(f"Gagal membuat kuitansi PDF: {e}")

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