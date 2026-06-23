import streamlit as st
import sqlite3
import datetime
import pandas as pd
from PIL import Image
import io
import hashlib

st.set_page_config(page_title="AVM Ciro Pro Portal", layout="wide")

# --- 1. OTURUM HAFIZASI KONTROLLERİ ---
if "giris_yapildi" not in st.session_state:
    st.session_state.update({
        "giris_yapildi": False, 
        "kullanici_turu": None, 
        "aktif_avm_id": None, 
        "aktif_avm_adi": None, 
        "aktif_magaza_id": None, 
        "aktif_magaza_adi": None
    })

# --- 2. GÜVENLİ VERİTABANI BAĞLANTISI (Cascade aktif edildi) ---
def vt_baglan():
    baglanti = sqlite3.connect("avm_veritabani.db", timeout=30)
    baglanti.execute("PRAGMA foreign_keys = ON") # SQLite için silme zincirini aktif tutar
    return baglanti

# --- 3. KRİPTOGRAFİK ŞİFRELEME ---
def sifre_hashle(sifre):
    return hashlib.sha256(sifre.encode('utf-8')).hexdigest()

# --- 4. VERİTABANI VE ŞEMA KURULUMU ---
def veritabani_hazirla():
    with vt_baglan() as baglanti:
        imlec = baglanti.cursor()
        imlec.execute("CREATE TABLE IF NOT EXISTS sistem_ayarlari (anahtar TEXT PRIMARY KEY, deger TEXT)")
        
        varsayilan_super_hash = sifre_hashle("esra123")
        imlec.execute("INSERT OR IGNORE INTO sistem_ayarlari (anahtar, deger) VALUES ('super_sifre', ?)", (varsayilan_super_hash,))

        imlec.execute("""
        CREATE TABLE IF NOT EXISTS avm_listesi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            avm_adi TEXT UNIQUE,
            lisans_bitis TEXT,
            odeme_durumu TEXT DEFAULT 'DENEME SÜRESİ',
            yonetici_sifre TEXT NOT NULL
        )""")

        imlec.execute("""
        CREATE TABLE IF NOT EXISTS magazalar (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            avm_id INTEGER,
            adi TEXT, 
            kat INTEGER,
            sifre TEXT NOT NULL,
            FOREIGN KEY(avm_id) REFERENCES avm_listesi(id) ON DELETE CASCADE
        )""")

        imlec.execute("""
        CREATE TABLE IF NOT EXISTS gunluk_cirolar (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            avm_id INTEGER,
            magaza_id INTEGER, 
            tarih TEXT, 
            kdv_dahil REAL, 
            kdv_haric REAL,
            kasa_foto BLOB,
            FOREIGN KEY(avm_id) REFERENCES avm_listesi(id) ON DELETE CASCADE,
            FOREIGN KEY(magaza_id) REFERENCES magazalar(id) ON DELETE CASCADE
        )""")
        baglanti.commit()

veritabani_hazirla()
tarih_bugun = datetime.date.today().strftime("%d-%m-%Y")

# ==============================================================================
# GİRİŞ EKRANI PANELI
# ==============================================================================
if not st.session_state["giris_yapildi"]:
    st.header("🔐 AVM Ciro Takip Portalı - Giriş Paneli")
    tur = st.selectbox("Kullanıcı Türü:", ["Mağaza Girişi", "AVM Yönetimi", "Süper Admin (Esra)"])
    
    if tur == "Süper Admin (Esra)":
        super_sifre_input = st.text_input("Süper Admin Giriş Şifresi:", type="password")
        if st.button("Süper Yönetim Paneline Giriş Yap"):
            with vt_baglan() as b:
                guncel_super_sifre = b.cursor().execute("SELECT deger FROM sistem_ayarlari WHERE anahtar = 'super_sifre'").fetchone()[0]
            if sifre_hashle(super_sifre_input) == guncel_super_sifre:
                st.session_state.update({"giris_yapildi": True, "kullanici_turu": "super"})
                st.rerun()
            else: st.error("❌ Hatalı Şifre!")

    elif tur == "AVM Yönetimi":
        with vt_baglan() as b:
            tum_avmler = b.cursor().execute("SELECT id, avm_adi FROM avm_listesi").fetchall()
        if tum_avmler:
            avm_sozluk = {a[1]: a[0] for a in tum_avmler}
            secilen_avm_adi = st.selectbox("Yöneticisi Olduğunuz AVM:", list(avm_sozluk.keys()))
            yonetim_sifre = st.text_input("Yönetici Giriş Şifresi:", type="password")
            if st.button("Yönetim Paneline Giriş Yap"):
                with vt_baglan() as b:
                    dogru_yonetim_hash = b.cursor().execute("SELECT yonetici_sifre FROM avm_listesi WHERE id = ?", (avm_sozluk[secilen_avm_adi],)).fetchone()[0]
                if sifre_hashle(yonetim_sifre) == dogru_yonetim_hash:
                    st.session_state.update({"giris_yapildi": True, "kullanici_turu": "yonetim", "aktif_avm_id": avm_sozluk[secilen_avm_adi], "aktif_avm_adi": secilen_avm_adi})
                    st.rerun()
                else: st.error("❌ Hatalı Şifre!")
        else: st.warning("Sistemde henüz kayıtlı AVM bulunmuyor.")
                
    elif tur == "Mağaza Girişi":
        with vt_baglan() as b:
            avm_ler = b.cursor().execute("SELECT id, avm_adi FROM avm_listesi").fetchall()
        if avm_ler:
            m_avm_sozluk = {a[1]: a[0] for a in avm_ler}
            g_secilen_avm = st.selectbox("Bulunduğunuz AVM:", list(m_avm_sozluk.keys()))
            with vt_baglan() as b:
                magazalar = b.cursor().execute("SELECT id, adi FROM magazalar WHERE avm_id = ?", (m_avm_sozluk[g_secilen_avm],)).fetchall()
            if magazalar:
                magaza_sozluk = {m[1]: m[0] for m in magazalar}
                secilen_magaza = st.selectbox("Mağazanız:", list(magaza_sozluk.keys()))
                magaza_sifre = st.text_input(f"{secilen_magaza} Şifresi:", type="password")
                if st.button("Mağaza Paneline Giriş Yap"):
                    with vt_baglan() as b:
                        dogru_magaza_hash = b.cursor().execute("SELECT sifre FROM magazalar WHERE id = ?", (magaza_sozluk[secilen_magaza],)).fetchone()[0]
                    if sifre_hashle(magaza_sifre) == dogru_magaza_hash:
                        st.session_state.update({"giris_yapildi": True, "kullanici_turu": "magaza", "aktif_avm_id": m_avm_sozluk[g_secilen_avm], "aktif_avm_adi": g_secilen_avm, "aktif_magaza_id": magaza_sozluk[secilen_magaza], "aktif_magaza_adi": secilen_magaza})
                        st.rerun()
                    else: st.error("❌ Hatalı Şifre!")
            else: st.warning("Bu AVM'ye ait mağaza bulunamadı.")

# ==============================================================================
# SİSTEM İÇİ PANEL ALANLARI
# ==============================================================================
else:
    col_baslik, col_cikis = st.columns([6, 1])
    with col_baslik: st.title("🏢 AVM Ciro Yönetim Portalı (SaaS)")
    with col_cikis:
        if st.button("🚪 Çıkış Yap"):
            st.session_state.update({"giris_yapildi": False, "kullanici_turu": None, "aktif_avm_id": None, "aktif_avm_adi": None, "aktif_magaza_id": None, "aktif_magaza_adi": None})
            st.rerun()
            
    st.markdown("---")

    # --------------------------------------------------------------------------
    # ROLE 1: SÜPER ADMIN PANELİ
    # --------------------------------------------------------------------------
    if st.session_state["kullanici_turu"] == "super":
        st.header("🏢 Süper Admin (Esra) Sağlayıcı Paneli")
        
        st.subheader("📋 Sistemdeki Tüm Müşteri AVM'ler")
        with vt_baglan() as b:
            df_avmler = pd.read_sql_query("SELECT id as [AVM ID], avm_adi as [AVM Adı], lisans_bitis as [Lisans Bitiş], odeme_durumu as [Ödeme Durumu] FROM avm_listesi", b)
        st.dataframe(df_avmler, use_container_width=True)
        
        if not df_avmler.empty:
            with st.expander("🗑️ Bir AVM'yi Sistemden Tamamen Kaldır"):
                silinecek_avm_adi = st.selectbox("Sistemden Silinecek AVM:", df_avmler["AVM Adı"].tolist())
                if st.button("🔴 Seçilen AVM'yi ve Tüm Verilerini SİL", type="primary"):
                    with vt_baglan() as b:
                        b.cursor().execute("DELETE FROM avm_listesi WHERE avm_adi = ?", (silinecek_avm_adi,))
                    st.success(f"'{silinecek_avm_adi}' ve tüm alt verileri veritabanından silindi.")
                    st.rerun()
        
        st.markdown("---")
        st.subheader("➕ Yeni Müşteri / AVM Ekle")
        c1, c2, c3, c4 = st.columns(4)
        with c1: yeni_avm_adi = st.text_input("Müşteri AVM Adı:")
        with c2: yeni_avm_lisans = st.date_input("Lisans Bitiş:", datetime.date.today() + datetime.timedelta(days=14))
        with c3: yeni_avm_odeme = st.selectbox("Ödeme Durumu:", ["DENEME SÜRESİ", "ÖDENDİ", "BEKLİYOR"])
        with c4: yeni_avm_admin_sifre = st.text_input("Yönetici Giriş Şifresi:", type="password", value="admin123")
            
        if st.button("🚀 Yeni AVM Tanımla"):
            if yeni_avm_adi.strip() != "":
                try:
                    with vt_baglan() as b:
                        b.cursor().execute("INSERT INTO avm_listesi (avm_adi, lisans_bitis, odeme_durumu, yonetici_sifre) VALUES (?, ?, ?, ?)", (yeni_avm_adi, yeni_avm_lisans.strftime("%Y-%m-%d"), yeni_avm_odeme, sifre_hashle(yeni_avm_admin_sifre)))
                    st.success(f"🎉 '{yeni_avm_adi}' başarıyla oluşturuldu!")
                    st.rerun()
                except Exception: st.error("Bu AVM adı zaten mevcut!")

    # --------------------------------------------------------------------------
    # ROLE 2: AVM YÖNETİCİ PANELİ
    # --------------------------------------------------------------------------
    elif st.session_state["kullanici_turu"] == "yonetim":
        a_id = st.session_state["aktif_avm_id"]
        a_adi = st.session_state["aktif_avm_adi"]
        
        with vt_baglan() as b:
            bitis_str, odeme_durumu = b.cursor().execute("SELECT lisans_bitis, odeme_durumu FROM avm_listesi WHERE id = ?", (a_id,)).fetchone()
        
        bitis_tarihi = datetime.datetime.strptime(bitis_str, "%Y-%m-%d").date()
        kalan_gun = (bitis_tarihi - datetime.date.today()).days
        
        if kalan_gun < 0:
            st.error(f"🚨 **ERİŞİM ENGELLENDİ:** Lisans süreniz dolmuştur! Sistem Sağlayıcınız (Esra) ile görüşün.")
            st.stop()

        secenek = st.sidebar.radio("Yönetim Menüsü:", ["📊 Raporlar & Grafikler", "📸 Kasa Fotoğrafları", "⚙️ Mağaza ve Şifre Ayarları"])
        
        if secenek == "📊 Raporlar & Grafikler":
            st.header(f"📊 {a_adi} Veri Analizi")
            with vt_baglan() as b:
                df_cirolar = pd.read_sql_query("SELECT c.tarih, m.adi as magaza_adi, m.kat, c.kdv_dahil, c.kdv_haric FROM gunluk_cirolar c JOIN magazalar m ON c.magaza_id = m.id WHERE c.avm_id = ?", b, params=(a_id,))
            if not df_cirolar.empty:
                st.bar_chart(df_cirolar.groupby("magaza_adi")["kdv_dahil"].sum())
                st.dataframe(df_cirolar, use_container_width=True)
            else: st.info("Henüz veri girişi yok.")
                
        elif secenek == "📸 Kasa Fotoğrafları":
            st.header("📸 Z-Raporu Denetimi")
            with vt_baglan() as b:
                veriler = b.cursor().execute("SELECT c.tarih, m.adi, c.kdv_dahil, c.kasa_foto FROM gunluk_cirolar c JOIN magazalar m ON c.magaza_id = m.id WHERE c.avm_id = ? ORDER BY c.id DESC", (a_id,)).fetchall()
            if veriler:
                for tarih, adi, ciro, foto_blob in veriler:
                    with st.expander(f"📷 {tarih} - {adi} ({ciro} TL)"):
                        if foto_blob: st.image(Image.open(io.BytesIO(foto_blob)), width=400)
            else: st.info("Fotoğraf bulunamadı.")

        elif secenek == "⚙️ Mağaza ve Şifre Ayarları":
            st.header("⚙️ Mağaza Yönetim Alanı")
            
            # ÖZELLİK: EXCEL ILE TOPLU MAĞAZA YÜKLEME SİHİRBAZI
            with st.expander("📥 Excel Dosyasından Toplu Mağaza Yükle (85 Mağaza İçin)"):
                st.markdown("""
                **🚨 Önemli Kurallar:**
                1. Yükleyeceğiniz Excel dosyasında şu 3 sütun ismi tam olarak yer almalıdır: `Mağaza Adı`, `Kat`, `Giriş Şifresi`
                2. Şifreleri Excel'e düz yazı (örn: 1234) yazabilirsiniz, sistem onları arka planda şifreleyecektir.
                """)
                yuklenen_excel = st.file_uploader("Excel Dosyası Seçin (.xlsx)", type=["xlsx"])
                if yuklenen_excel is not None:
                    try:
                        df_ex = pd.read_excel(yuklenen_excel)
                        gerekli_sutunlar = ["Mağaza Adı", "Kat", "Giriş Şifresi"]
                        
                        if all(col in df_ex.columns for col in gerekli_sutunlar):
                            if st.button("🚀 Excel'deki Tüm Mağazaları Sisteme Aktar"):
                                basarili_kayit = 0
                                with vt_baglan() as b:
                                    imlec = b.cursor()
                                    for _, satir in df_ex.iterrows():
                                        m_adi_ex = str(satir["Mağaza Adı"]).strip()
                                        m_kat_ex = int(satir["Kat"])
                                        m_sifre_ex = str(satir["Giriş Şifresi"]).strip()
                                        
                                        if m_adi_ex:
                                            imlec.execute("INSERT INTO magazalar (avm_id, adi, kat, sifre) VALUES (?, ?, ?, ?)", 
                                                           (a_id, m_adi_ex, m_kat_ex, sifre_hashle(m_sifre_ex)))
                                            basarili_kayit += 1
                                    b.commit()
                                st.success(f"🎉 Harika! {basarili_kayit} adet mağaza Excel listesinden başarıyla içeri aktarıldı.")
                                st.rerun()
                        else:
                            st.error("🚨 Sütun isimleri uyuşmuyor! Excel'de sütun başlıkları 'Mağaza Adı', 'Kat' and 'Giriş Şifresi' olmalıdır.")
                    except Exception as e:
                        st.error(f"Excel okunurken bir sorun oluştu: {e}")

            st.markdown("---")
            
            # TEKİL MAĞAZA EKLEME
            with st.expander("➕ Tek Tek Yeni Mağaza Ekle"):
                yeni_m_adi = st.text_input("Mağaza Adı:")
                yeni_m_kat = st.number_input("Kat:", min_value=-2, max_value=5, value=0)
                yeni_m_sifre = st.text_input("Mağaza Şifresi:", value="1234")
                if st.button("Mağazayı Kaydet"):
                    if yeni_m_adi.strip() != "":
                        with vt_baglan() as b:
                            b.cursor().execute("INSERT INTO magazalar (avm_id, adi, kat, sifre) VALUES (?, ?, ?, ?)", (a_id, yeni_m_adi, yeni_m_kat, sifre_hashle(yeni_m_sifre)))
                        st.success(f"✓ {yeni_m_adi} eklendi.")
                        st.rerun()
            
            st.markdown("---")
            
            # MAĞAZA SİLME
            with st.expander("🗑️ Mağaza Sil / Sistemden Çıkar"):
                with vt_baglan() as b:
                    mevcut_magazalar = b.cursor().execute("SELECT id, adi FROM magazalar WHERE avm_id = ?", (a_id,)).fetchall()
                if mevcut_magazalar:
                    m_sil_sozluk = {m[1]: m[0] for m in mevcut_magazalar}
                    silinecek_m_adi = st.selectbox("Sistemden Çıkarılacak Mağaza:", list(m_sil_sozluk.keys()))
                    if st.button("🔴 Mağazayı ve Geçmiş Cirolarını Sil", type="primary"):
                        with vt_baglan() as b:
                            b.cursor().execute("DELETE FROM magazalar WHERE id = ?", (m_sil_sozluk[silinecek_m_adi],))
                        st.success(f"'{silinecek_m_adi}' mağazası tüm ciro geçmişiyle birlikte silindi.")
                        st.rerun()
                else: st.info("Henüz kayıtlı mağaza yok.")

    # --------------------------------------------------------------------------
    # ROLE 3: MAĞAZA PANELİ
    # --------------------------------------------------------------------------
    elif st.session_state["kullanici_turu"] == "magaza":
        a_id = st.session_state["aktif_avm_id"]
        m_id = st.session_state["aktif_magaza_id"]
        m_adi = st.session_state["aktif_magaza_adi"]
        
        sekme_giris, sekme_rapor = st.tabs(["💰 Günlük Ciro Girişi", "📅 Geçmiş Raporlar"])
        
        with sekme_giris:
            st.header(f"🛍️ {m_adi} Veri Girişi")
            with vt_baglan() as b:
                giris_var_mi = b.cursor().execute("SELECT COUNT(*) FROM gunluk_cirolar WHERE magaza_id = ? AND tarih = ?", (m_id, tarih_bugun)).fetchone()[0]
            
            if giris_var_mi > 0: st.success("🎉 Bugün için ciro girişiniz zaten yapılmıştır.")
            else:
                kdv_dahil = st.number_input("KDV Dahil Ciro:", min_value=0.0, step=100.0)
                kdv_haric = st.number_input("KDV Hariç Ciro:", min_value=0.0, step=100.0)
                yuklenen_dosya = st.file_uploader("📸 Z-Raporu Fotoğrafı:", type=["png", "jpg", "jpeg"])
                
                if st.button("Ciroyu Gönder"):
                    if yuklenen_dosya is not None:
                        foto_byte = yuklenen_dosya.read()
                        with vt_baglan() as b:
                            b.cursor().execute("INSERT INTO gunluk_cirolar (avm_id, magaza_id, tarih, kdv_dahil, kdv_haric, kasa_foto) VALUES (?, ?, ?, ?, ?, ?)", (a_id, m_id, tarih_bugun, kdv_dahil, kdv_haric, sqlite3.Binary(foto_byte)))
                        st.success("Veriler işlendi!")
                        st.rerun()
                    else: st.error("Lütfen fotoğraf yükleyin!")
                        
        with sekme_rapor:
            with vt_baglan() as b:
                df_magaza_ozel = pd.read_sql_query("SELECT tarih, kdv_dahil, kdv_haric FROM gunluk_cirolar WHERE magaza_id = ? ORDER BY id DESC", b, params=(m_id,))
            if not df_magaza_ozel.empty: st.dataframe(df_magaza_ozel, use_container_width=True)
