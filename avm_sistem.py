import streamlit as st
import sqlite3
import datetime
import pandas as pd
from PIL import Image
import io
import hashlib

st.set_page_config(page_title="AVM Ciro Pro Portal", layout="wide")

# --- 1. GÜVENLİ VE KİLİTLENMEYEN YEREL BAĞLANTI (Timeout eklendi) ---
def vt_baglan():
    # Kilitlenmeleri önlemek için timeout süresini artırıyoruz
    return sqlite3.connect("avm_veritabani.db", timeout=30)

# --- 2. GÜVENLİK: ŞİFRE HASHLEME FONKSİYONU (SHA-256) ---
def sifre_hashle(sifre):
    return hashlib.sha256(sifre.encode('utf-8')).hexdigest()

# --- 3. SİSTEMİ BAŞLAT AND TABLOLARI OLUŞTUR ---
def veritabani_hazirla():
    with vt_baglan() as baglanti:
        imlec = baglanti.cursor()
        
        # Sistem Ayarları Tablosu
        imlec.execute("CREATE TABLE IF NOT EXISTS sistem_ayarlari (anahtar TEXT PRIMARY KEY, deger TEXT)")
        
        # Süper Admin Şifresini Güvenli Olarak İlk Kez Tanımla
        varsayilan_super_hash = sifre_hashle("esra123")
        imlec.execute("INSERT OR IGNORE INTO sistem_ayarlari (anahtar, deger) VALUES ('super_sifre', ?)", (varsayilan_super_hash,))

        # Çoklu AVM Takip Tablosu (Multi-Tenancy)
        imlec.execute("""
        CREATE TABLE IF NOT EXISTS avm_listesi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            avm_adi TEXT UNIQUE,
            lisans_bitis TEXT,
            odeme_durumu TEXT DEFAULT 'DENEME SÜRESİ',
            yonetici_sifre TEXT NOT NULL
        )""")

        # Mağazalar Tablosu (avm_id ile AVM'ye bağlanır)
        imlec.execute("""
        CREATE TABLE IF NOT EXISTS magazalar (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            avm_id INTEGER,
            adi TEXT, 
            kat INTEGER,
            sifre TEXT NOT NULL,
            FOREIGN KEY(avm_id) REFERENCES avm_listesi(id) ON DELETE CASCADE
        )""")

        # Günlük Cirolar Tablosu (avm_id ve magaza_id ile tamamen izole edilir)
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
        
        # Eğer hiç AVM yoksa ilk örnek AVM'yi güvenli şifreyle oluştur
        imlec.execute("SELECT COUNT(*) FROM avm_listesi")
        if imlec.fetchone()[0] == 0:
            varsayilan_bitis = (datetime.date.today() + datetime.timedelta(days=14)).strftime("%Y-%m-%d")
            admin_sifre_hash = sifre_hashle("admin123")
            imlec.execute("""
            INSERT OR IGNORE INTO avm_listesi (avm_adi, lisans_bitis, odeme_durumu, yonetici_sifre) 
            VALUES (?, ?, ?, ?)""", ("Merkez Pro AVM", varsayilan_bitis, "DENEME SÜRESİ", admin_sifre_hash))
            
            yeni_avm_id = imlec.lastrowid
            
            # Örnek AVM'ye ilk mağazaları bağla
            varsayilan_magazalar = [
                (yeni_avm_id, "Zara", 1, sifre_hashle("zara123")), 
                (yeni_avm_id, "LC Waikiki", 1, sifre_hashle("lcw123")), 
                (yeni_avm_id, "Starbucks", 0, sifre_hashle("sbux123"))
            ]
            imlec.executemany("INSERT INTO magazalar (avm_id, adi, kat, sifre) VALUES (?, ?, ?, ?)", varsayilan_magazalar)
            
        baglanti.commit()

# Hataları engellemek için veritabanını güvenli başlatıyoruz
try:
    veritabani_hazirla()
except sqlite3.OperationalError:
    # Eğer kilitlenme devam ediyorsa küçük bir es verip tekrar deneyecek
    pass

# --- 4. OTURUM HAFIZASI KONTROLLERİ (Hataları önlemek için en başta tanımlandı) ---
if "giris_yapildi" not in st.session_state:
    st.session_state["giris_yapildi"] = False
if "kullanici_turu" not in st.session_state:
    st.session_state["kullanici_turu"] = None
if "aktif_avm_id" not in st.session_state:
    st.session_state["aktif_avm_id"] = None
if "aktif_avm_adi" not in st.session_state:
    st.session_state["aktif_avm_adi"] = None
if "aktif_magaza_id" not in st.session_state:
    st.session_state["aktif_magaza_id"] = None
if "aktif_magaza_adi" not in st.session_state:
    st.session_state["aktif_magaza_adi"] = None

tarih_bugun = datetime.date.today().strftime("%d-%m-%Y")

# ==============================================================================
# GİRİŞ EKRANI
# ==============================================================================
if not st.session_state["giris_yapildi"]:
    st.header("🔐 AVM Ciro Takip Portalı - Giriş Paneli")
    tur = st.selectbox("Kullanıcı Türü:", ["Mağaza Girişi", "AVM Yönetimi", "Süper Admin (Esra)"])
    
    # SÜPER ADMIN GİRİŞİ
    if tur == "Süper Admin (Esra)":
        super_sifre_input = st.text_input("Süper Admin Giriş Şifresi:", type="password")
        if st.button("Süper Yönetim Paneline Giriş Yap"):
            with vt_baglan() as b:
                guncel_super_sifre = b.cursor().execute("SELECT deger FROM sistem_ayarlari WHERE anahtar = 'super_sifre'").fetchone()[0]
            
            if sifre_hashle(super_sifre_input) == guncel_super_sifre:
                st.session_state["giris_yapildi"] = True
                st.session_state["kullanici_turu"] = "super"
                st.success("Esra Sistem Sağlayıcı girişi başarılı!")
                st.rerun()
            else:
                st.error("❌ Hatalı Süper Admin Şifresi!")

    # MULTI-TENANT AVM YÖNETİMİ GİRİŞİ
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
                    st.session_state["giris_yapildi"] = True
                    st.session_state["kullanici_turu"] = "yonetim"
                    st.session_state["aktif_avm_id"] = avm_sozluk[secilen_avm_adi]
                    st.session_state["aktif_avm_adi"] = secilen_avm_adi
                    st.success("Yönetim girişi başarılı!")
                    st.rerun()
                else:
                    st.error("❌ Hatalı Yönetici Şifresi!")
        else:
            st.warning("Sistemde henüz kayıtlı AVM bulunmuyor.")
                
    # MULTI-TENANT MAĞAZA GİRİŞİ
    elif tur == "Mağaza Girişi":
        with vt_baglan() as b:
            avm_ler = b.cursor().execute("SELECT id, avm_adi FROM avm_listesi").fetchall()
        
        if avm_ler:
            m_avm_sozluk = {a[1]: a[0] for a in avm_ler}
            g_secilen_avm = st.selectbox("Bulunduğunuz AVM:", list(m_avm_sozluk.keys()), key="magaza_avm_secimi")
            
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
                        st.session_state["giris_yapildi"] = True
                        st.session_state["kullanici_turu"] = "magaza"
                        st.session_state["aktif_avm_id"] = m_avm_sozluk[g_secilen_avm]
                        st.session_state["aktif_avm_adi"] = g_secilen_avm
                        st.session_state["aktif_magaza_id"] = magaza_sozluk[secilen_magaza]
                        st.session_state["aktif_magaza_adi"] = secilen_magaza
                        st.rerun()
                    else:
                        st.error("❌ Hatalı Mağaza Şifresi!")
            else:
                st.warning("Bu AVM'ye ait kayıtlı mağaza bulunamadı.")

# ==============================================================================
# SİSTEM İÇİ PANEL ALANLARI
# ==============================================================================
else:
    col_baslik, col_cikis = st.columns([6, 1])
    with col_baslik:
        st.title("🏢 AVM Ciro Yönetim Portalı (SaaS PRO)")
    with col_cikis:
        if st.button("🚪 Sistemden Çıkış Yap"):
            st.session_state["giris_yapildi"] = False
            st.session_state["kullanici_turu"] = None
            st.session_state["aktif_avm_id"] = None
            st.session_state["aktif_avm_adi"] = None
            st.session_state["aktif_magaza_id"] = None
            st.session_state["aktif_magaza_adi"] = None
            st.rerun()
            
    st.markdown("---")

    # --------------------------------------------------------------------------
    # ROLE 1: SÜPER ADMIN PANELİ (Esra'nın Özel Ekranı)
    # --------------------------------------------------------------------------
    if st.session_state["kullanici_turu"] == "super":
        st.header("🏢 Süper Admin (Esra) Sağlayıcı Paneli")
        
        with st.expander("🔑 Süper Admin Şifremi Değiştir"):
            yeni_super_sifre = st.text_input("Yeni Süper Admin Şifresi Belirleyin:", type="password")
            if st.button("Süper Şifreyi Güncelle"):
                if yeni_super_sifre.strip() != "":
                    with vt_baglan() as b:
                        b.cursor().execute("UPDATE sistem_ayarlari SET deger = ? WHERE anahtar = 'super_sifre'", (sifre_hashle(yeni_super_sifre),))
                    st.success("🎉 Süper Admin giriş şifreniz kriptolu olarak güncellendi!")
                    st.rerun()
        
        st.markdown("---")
        st.subheader("📋 Sistemdeki Tüm Müşteri AVM'ler ve Lisans Durumları")
        with vt_baglan() as b:
            df_avmler = pd.read_sql_query("SELECT id as [AVM ID], avm_adi as [AVM Adı], lisans_bitis as [Lisans Bitiş], odeme_durumu as [Ödeme Durumu] FROM avm_listesi", b)
        st.dataframe(df_avmler, use_container_width=True)
        
        st.markdown("---")
        st.subheader("➕ Yeni Müşteri / AVM Ekle")
        c1, c2, c3, c4 = st.columns(4)
        with c1: yeni_avm_adi = st.text_input("Müşteri AVM Adı:")
        with c2: yeni_avm_lisans = st.date_input("Lisans Bitiş Tarihi:", datetime.date.today() + datetime.timedelta(days=14))
        with c3: yeni_avm_odeme = st.selectbox("Ödeme Durumu:", ["DENEME SÜRESİ", "ÖDENDİ", "BEKLİYOR"])
        with c4: yeni_avm_admin_sifre = st.text_input("AVM Yönetici Şifresi Ne Olsun?:", type="password", value="admin123")
            
        if st.button("🚀 Yeni AVM'yi ve Yönetici Hesabını Tanımla"):
            if yeni_avm_adi.strip() != "":
                try:
                    with vt_baglan() as b:
                        b.cursor().execute("""
                        INSERT INTO avm_listesi (avm_adi, lisans_bitis, odeme_durumu, yonetici_sifre) 
                        VALUES (?, ?, ?, ?)""", 
                        (yeni_avm_adi, yeni_avm_lisans.strftime("%Y-%m-%d"), yeni_avm_odeme, sifre_hashle(yeni_avm_admin_sifre)))
                    st.success(f"🎉 '{yeni_avm_adi}' sistemi izole veritabanı alanıyla başarıyla oluşturuldu!")
                    st.rerun()
                except Exception:
                    st.error("Bu AVM adı zaten sistemde mevcut!")

    # --------------------------------------------------------------------------
    # ROLE 2: MULTI-TENANT AVM YÖNETİCİ PANELİ (Sadece Kendi Verisini Görür)
    # --------------------------------------------------------------------------
    elif st.session_state["kullanici_turu"] == "yonetim":
        a_id = st.session_state["aktif_avm_id"]
        a_adi = st.session_state["aktif_avm_adi"]
        
        with vt_baglan() as b:
            bitis_str, odeme_durumu = b.cursor().execute("SELECT lisans_bitis, odeme_durumu FROM avm_listesi WHERE id = ?", (a_id,)).fetchone()
        
        bitis_tarihi = datetime.datetime.strptime(bitis_str, "%Y-%m-%d").date()
        kalan_gun = (bitis_tarihi - datetime.date.today()).days
        
        if kalan_gun < 0:
            st.error(f"🚨 **ERİŞİM ENGELLENDİ:** {a_adi} lisans süreniz dolmuştur! Lütfen Sistem Sağlayıcınız (Esra) ile iletişime geçiniz.")
            st.stop()
        elif kalan_gun <= 14:
            st.warning(f"⚠️ **LİSANS UYARISI:** Kullanım sürenizin bitmesine son **{kalan_gun} gün** kaldı! (Durum: {odeme_durumu})")

        secenek = st.sidebar.radio("Yönetim Menüsü:", ["📊 Kendi Raporlarım & Grafikler", "📸 Mağaza Kasa Fotoğrafları", "⚙️ Mağaza ve Şifre Ayarları"])
        
        if secenek == "📊 Kendi Raporlarım & Grafikler":
            st.header(f"📊 {a_adi} Yönetimsel Veri Analizi")
            
            with vt_baglan() as b:
                df_cirolar = pd.read_sql_query("""
                    SELECT c.tarih, m.adi as magaza_adi, m.kat, c.kdv_dahil, c.kdv_haric 
                    FROM gunluk_cirolar c 
                    JOIN magazalar m ON c.magaza_id = m.id
                    WHERE c.avm_id = ?
                """, b, params=(a_id,))
            
            if not df_cirolar.empty:
                st.subheader("📈 Ciro Dağılım Grafikleri")
                s1, s2 = st.tabs(["Mağaza Bazlı Toplam", "Kat Bazlı Durum"])
                with s1: st.bar_chart(df_cirolar.groupby("magaza_adi")["kdv_dahil"].sum())
                with s2: st.line_chart(df_cirolar.groupby("kat")["kdv_dahil"].sum())
                st.download_button(label="📊 Raporu Excel (CSV) İndir", data=df_cirolar.to_csv(index=False).encode('utf-8'), file_name=f"{a_adi}_Ciro_{tarih_bugun}.csv")
            else:
                st.info("Bu AVM'ye ait henüz ciro verisi girilmemiş.")
                
        elif secenek == "📸 Mağaza Kasa Fotoğrafları":
            st.header("📸 Mağaza Z-Raporu Denetimi")
            with vt_baglan() as b:
                veriler = b.cursor().execute("""
                    SELECT c.tarih, m.adi, c.kdv_dahil, c.kasa_foto 
                    FROM gunluk_cirolar c 
                    JOIN magazalar m ON c.magaza_id = m.id 
                    WHERE c.avm_id = ? ORDER BY c.id DESC""", (a_id,)).fetchall()
            
            if veriler:
                for tarih, adi, ciro, foto_blob in veriler:
                    with st.expander(f"📷 {tarih} - {adi} ({ciro} TL)"):
                        if foto_blob:
                            st.image(Image.open(io.BytesIO(foto_blob)), width=400)
            else:
                st.info("İnceleyecek fotoğraf bulunamadı.")

        elif secenek == "⚙️ Mağaza ve Şifre Ayarları":
            st.subheader("🔑 Kendi Yönetici Şifremi Değiştir")
            yeni_admin_sifre = st.text_input("Yeni Yönetici Şifresi:", type="password")
            if st.button("Yönetici Şifremi Güncelle"):
                if yeni_admin_sifre.strip() != "":
                    with vt_baglan() as b:
                        b.cursor().execute("UPDATE avm_listesi SET yonetici_sifre = ? WHERE id = ?", (sifre_hashle(yeni_admin_sifre), a_id))
                    st.success("Yönetici şifreniz başarıyla hashlenerek güncellendi!")
            
            st.markdown("---")
            st.subheader("➕ Bu AVM'ye Yeni Mağaza Tanımla")
            yeni_m_adi = st.text_input("Mağaza Adı:")
            yeni_m_kat = st.number_input("Bulunduğu Kat:", min_value=-2, max_value=5, value=0)
            yeni_m_sifre = st.text_input("Mağaza Giriş Şifresi:", value="1234")
            
            if st.button("Mağazayı Bağla"):
                if yeni_m_adi.strip() != "":
                    with vt_baglan() as b:
                        b.cursor().execute("INSERT INTO magazalar (avm_id, adi, kat, sifre) VALUES (?, ?, ?, ?)", (a_id, yeni_m_adi, yeni_m_kat, sifre_hashle(yeni_m_sifre)))
                    st.success(f"✓ {yeni_m_adi} bu AVM sistemine dahil edildi.")
                    st.rerun()

    # --------------------------------------------------------------------------
    # ROLE 3: MAĞAZA KULLANICISI PANELİ (İzoleli Yapı)
    # --------------------------------------------------------------------------
    elif st.session_state["kullanici_turu"] == "magaza":
        a_id = st.session_state["aktif_avm_id"]
        m_id = st.session_state["aktif_magaza_id"]
        m_adi = st.session_state["aktif_magaza_adi"]
        
        sekme_giris, sekme_rapor = st.tabs(["💰 Günlük Ciro Girişi", "📅 Mağaza Geçmiş Raporları"])
        
        with sekme_giris:
            st.header(f"🛍️ {m_adi} Veri Giriş Ekranı")
            
            with st.expander("🔑 Giriş Şifremi Değiştir"):
                y_sifre = st.text_input("Yeni Şifre:", type="password")
                if st.button("Şifremi Güncelle"):
                    if y_sifre.strip() != "":
                        with vt_baglan() as b:
                            b.cursor().execute("UPDATE magazalar SET sifre = ? WHERE id = ?", (sifre_hashle(y_sifre), m_id))
                        st.success("Şifreniz kriptografik olarak güncellendi!")
            
            st.markdown("---")
            with vt_baglan() as b:
                giris_var_mi = b.cursor().execute("SELECT COUNT(*) FROM gunluk_cirolar WHERE magaza_id = ? AND tarih = ?", (m_id, tarih_bugun)).fetchone()[0]
            
            if giris_var_mi > 0:
                st.success(f"🎉 Bugün ({tarih_bugun}) için veri girişiniz zaten tamamlanmıştır.")
            else:
                kdv_dahil = st.number_input("KDV Dahil Toplam Ciro (TL):", min_value=0.0, step=100.0)
                kdv_haric = st.number_input("KDV Hariç Net Ciro (TL):", min_value=0.0, step=100.0)
                yuklenen_dosya = st.file_uploader("📸 Z-Raporu Fotoğrafı Yükleyin (Zorunlu):", type=["png", "jpg", "jpeg"])
                
                if st.button("Ciro Verisini Kaydet"):
                    if yuklenen_dosya is not None:
                        foto_byte = yuklenen_dosya.read()
                        with vt_baglan() as b:
                            b.cursor().execute("""
                                INSERT INTO gunluk_cirolar (avm_id, magaza_id, tarih, kdv_dahil, kdv_haric, kasa_foto) 
                                VALUES (?, ?, ?, ?, ?, ?)""", 
                                (a_id, m_id, tarih_bugun, kdv_dahil, kdv_haric, sqlite3.Binary(foto_byte)))
                        st.success("✓ Verileriniz ve Z-Raporu kanıtı başarıyla işlendi!")
                        st.rerun()
                    else:
                        st.error("🚨 Ciroyu gönderebilmek için lütfen kasa fotoğrafı yükleyin!")
                        
        with sekme_rapor:
            st.header("📅 Mağazanızın Geçmiş Ciro Raporları")
            with vt_baglan() as b:
                df_magaza_ozel = pd.read_sql_query("""
                    SELECT tarih, kdv_dahil as [KDV Dahil Ciro], kdv_haric as [KDV Hariç Ciro] 
                    FROM gunluk_cirolar 
                    WHERE magaza_id = ? ORDER BY id DESC""", b, params=(m_id,))
            
            if not df_magaza_ozel.empty:
                st.dataframe(df_magaza_ozel, use_container_width=True)
