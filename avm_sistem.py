import streamlit as st
import sqlite3
import datetime
import pandas as pd
from PIL import Image
import io

st.set_page_config(page_title="AVM Ciro Pro Portal", layout="wide")

def vt_baglan():
    baglanti = sqlite3.connect("avm_veritabani.db")
    return baglanti, baglanti.cursor()

# 1. VERİTABANI VE TABLOLARIN OLUŞTURULMASI
baglanti, imlec = vt_baglan()
imlec.execute("""
CREATE TABLE IF NOT EXISTS magazalar (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    adi TEXT, 
    kat INTEGER,
    sifre TEXT DEFAULT '1234'
)""")

# gunluk_cirolar tablosuna foto_yolu (BLOB/Binary veri türü) eklendi
imlec.execute("""
CREATE TABLE IF NOT EXISTS gunluk_cirolar (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    magaza_id INTEGER, 
    tarih TEXT, 
    kdv_dahil REAL, 
    kdv_haric REAL,
    kasa_foto BLOB
)""")

# Yönetici şifresini veritabanında tutmak için yeni bir ayarlar tablosu
imlec.execute("CREATE TABLE IF NOT EXISTS sistem_ayarlari (anahtar TEXT PRIMARY KEY, deger TEXT)")
imlec.execute("INSERT OR IGNORE INTO sistem_ayarlari (anahtar, deger) VALUES ('yonetici_sifre', 'admin123')")

imlec.execute("SELECT COUNT(*) FROM magazalar")
if imlec.fetchone()[0] == 0:
    varsayilan_magazalar = [("Zara", 1, "zara123"), ("LC Waikiki", 1, "lcw123"), ("Starbucks", 0, "sbux123"), ("Teknosa", 2, "tekno123")]
    imlec.executemany("INSERT INTO magazalar (adi, kat, sifre) VALUES (?, ?, ?)", varsayilan_magazalar)
    baglanti.commit()
baglanti.close()

# Oturum Hafızası Kontrolleri
if "giris_yapildi" not in st.session_state:
    st.session_state["giris_yapildi"] = False
if "kullanici_turu" not in st.session_state:
    st.session_state["kullanici_turu"] = None
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
    
    tur = st.selectbox("Kullanıcı Türü:", ["Mağaza Girişi", "AVM Yönetimi"])
    
    if tur == "AVM Yönetimi":
        yonetim_sifre = st.text_input("Yönetici Giriş Şifresi:", type="password")
        if st.button("Yönetim Paneline Giriş Yap"):
            baglanti, imlec = vt_baglan()
            imlec.execute("SELECT deger FROM sistem_ayarlari WHERE anahtar = 'yonetici_sifre'")
            guncel_admin_sifre = imlec.fetchone()[0]
            baglanti.close()
            
            if yonetim_sifre == guncel_admin_sifre:
                st.session_state["giris_yapildi"] = True
                st.session_state["kullanici_turu"] = "yonetim"
                st.success("Yönetim girişi başarılı!")
                st.rerun()
            else:
                st.error("❌ Hatalı Yönetici Şifresi!")
                
    elif tur == "Mağaza Girişi":
        baglanti, imlec = vt_baglan()
        imlec.execute("SELECT id, adi FROM magazalar")
        magazalar = imlec.fetchall()
        baglanti.close()
        
        if len(magazalar) == 0:
            st.warning("Sistemde kayıtlı mağaza bulunamadı.")
        else:
            magaza_sozluk = {m[1]: m[0] for m in magazalar}
            secilen_magaza = st.selectbox("Mağazanız:", list(magaza_sozluk.keys()))
            magaza_sifre = st.text_input(f"{secilen_magaza} Mağaza Şifresi:", type="password")
            
            if st.button("Mağaza Paneline Giriş Yap"):
                baglanti, imlec = vt_baglan()
                imlec.execute("SELECT sifre FROM magazalar WHERE id = ?", (magaza_sozluk[secilen_magaza],))
                dogru_sifre = imlec.fetchone()[0]
                baglanti.close()
                
                if magaza_sifre == dogru_sifre:
                    st.session_state["giris_yapildi"] = True
                    st.session_state["kullanici_turu"] = "magaza"
                    st.session_state["aktif_magaza_id"] = magaza_sozluk[secilen_magaza]
                    st.session_state["aktif_magaza_adi"] = secilen_magaza
                    st.rerun()
                else:
                    st.error("❌ Hatalı Mağaza Şifresi!")

# ==============================================================================
# SİSTEM İÇİ (Giriş Sonrası)
# ==============================================================================
else:
    col_baslik, col_cikis = st.columns([6, 1])
    with col_baslik:
        st.title("🏢 AVM Ciro Yönetim ve Analiz Portalı (PRO)")
    with col_cikis:
        if st.button("🚪 Sistemden Çıkış Yap"):
            st.session_state["giris_yapildi"] = False
            st.session_state["kullanici_turu"] = None
            st.session_state["aktif_magaza_id"] = None
            st.session_state["aktif_magaza_adi"] = None
            st.rerun()
            
    st.markdown("---")

    # ROLE 1: MAĞAZA KULLANICISI PANELİ
    if st.session_state["kullanici_turu"] == "magaza":
        m_id = st.session_state["aktif_magaza_id"]
        m_adi = st.session_state["aktif_magaza_adi"]
        
        # Sekmeler oluşturuyoruz: Giriş Yap ve Geçmiş Raporlar
        sekme_giris, sekme_rapor = st.tabs(["💰 Günlük Ciro Girişi", "📅 Mağaza Geçmiş Raporları"])
        
        with sekme_giris:
            st.header(f"🛍️ {m_adi} Veri Giriş Ekranı")
            
            with st.expander("🔑 Giriş Şifremi Değiştir"):
                yeni_sifre = st.text_input("Yeni Şifre:", type="password")
                if st.button("Şifremi Güncelle"):
                    if yeni_sifre.strip() != "":
                        baglanti, imlec = vt_baglan()
                        imlec.execute("UPDATE magazalar SET sifre = ? WHERE id = ?", (yeni_sifre, m_id))
                        baglanti.commit()
                        baglanti.close()
                        st.success("🎉 Şifreniz başarıyla değiştirildi!")
                    else:
                        st.error("Şifre alanı boş bırakılamaz!")
            
            st.markdown("---")
            
            baglanti, imlec = vt_baglan()
            imlec.execute("SELECT COUNT(*) FROM gunluk_cirolar WHERE magaza_id = ? AND tarih = ?", (m_id, tarih_bugun))
            giris_var_mi = imlec.fetchone()[0]
            baglanti.close()
            
            if giris_var_mi > 0:
                st.success(f"🎉 Harika! {m_adi} için bugün ({tarih_bugun}) ciro girişi zaten tamamlanmış.")
            else:
                st.warning("⚠️ Bugünün ciro verisi henüz sisteme girilmemiş.")
                
                kdv_dahil = st.number_input("KDV Dahil Toplam Ciro (TL):", min_value=0.0, step=500.0)
                kdv_haric = st.number_input("KDV Hariç Net Ciro (TL):", min_value=0.0, step=500.0)
                
                # FOTOĞRAF YÜKLEME ALANI
                yuklenen_dosya = st.file_uploader("📸 Kasa Raporu / Z-Raporu Fotoğrafı Yükleyin (Zorunlu):", type=["png", "jpg", "jpeg"])
                
                if st.button("Ciro Verisini ve Fotoğrafı Güvenli Gönder"):
                    if yuklenen_dosya is not None:
                        # Fotoğrafı veritabanına kaydetmek için byte formatına çeviriyoruz
                        foto_byte = yuklenen_dosya.read()
                        
                        baglanti, imlec = vt_baglan()
                        imlec.execute("""
                            INSERT INTO gunluk_cirolar (magaza_id, tarih, kdv_dahil, kdv_haric, kasa_foto) 
                            VALUES (?, ?, ?, ?, ?)""", 
                            (m_id, tarih_bugun, kdv_dahil, kdv_haric, foto_byte))
                        baglanti.commit()
                        baglanti.close()
                        st.success("✓ Ciro verisi ve kasa fotoğrafı başarıyla veritabanına kilitlendi!")
                        st.rerun()
                    else:
                        st.error("🚨 Ciroyu gönderebilmek için lütfen kasa fotoğrafı yükleyin!")
                        
        with sekme_rapor:
            st.header("📅 Mağazanızın Geçmiş Ciro Raporları")
            baglanti, imlec = vt_baglan()
            df_magaza_ozel = pd.read_sql_query("""
                SELECT tarih, kdv_dahil as [KDV Dahil Ciro], kdv_haric as [KDV Hariç Ciro] 
                FROM gunluk_cirolar 
                WHERE magaza_id = ? ORDER BY id DESC""", baglanti, params=(m_id,))
            baglanti.close()
            
            if not df_magaza_ozel.empty:
                st.dataframe(df_magaza_ozel, use_container_width=True)
            else:
                st.info("Henüz geçmiş günlere ait bir ciro veriniz bulunmuyor.")

    # ROLE 2: YÖNETİCİ PANELİ
    elif st.session_state["kullanici_turu"] == "yonetim":
        secenek = st.sidebar.radio("Yönetim Menüsü:", ["📊 Genel Raporlar & Grafikler", "📸 Kasa Fotoğrafları Denetimi", "⚙️ AVM Yönetim Ayarları"])
        
        if secenek == "📊 Genel Raporlar & Grafikler":
            st.header(f"📊 AVM Yönetim Raporları Paneli")
            
            baglanti, imlec = vt_baglan()
            df_cirolar = pd.read_sql_query("""
                SELECT c.tarih, m.adi as magaza_adi, m.kat, c.kdv_dahil, c.kdv_haric 
                FROM gunluk_cirolar c 
                JOIN magazalar m ON c.magaza_id = m.id
            """, baglanti)
            
            imlec.execute("SELECT id, adi, kat FROM magazalar")
            tum_magazalar = imlec.fetchall()
            imlec.execute("SELECT magaza_id FROM gunluk_cirolar WHERE tarih = ?", (tarih_bugun,))
            bugun_girenler = [satir[0] for satir in imlec.fetchall()]
            baglanti.close()
            
            if not df_cirolar.empty:
                excel_verisi = df_cirolar.to_csv(index=False).encode('utf-8')
                st.download_button(label="📊 Tüm Raporu Excel (CSV) Olarak İndir", data=excel_verisi, file_name=f"AVM_Ciro_Raporu_{tarih_bugun}.csv", mime="text/csv")
                
            st.subheader("📈 Görsel Analiz Grafikleri")
            if not df_cirolar.empty:
                sekme1, sekme2 = st.tabs(["Mağaza Bazlı Toplam Ciro", "Kat Bazlı Yoğunluk"])
                with sekme1: st.bar_chart(df_cirolar.groupby("magaza_adi")["kdv_dahil"].sum())
                with sekme2: st.line_chart(df_cirolar.groupby("kat")["kdv_dahil"].sum())
                
            st.markdown("---")
            st.subheader("🚨 Bugünün Durum Kontrolü")
            col1, col2 = st.columns(2)
            with col1:
                st.success("✅ Bugün Giriş Yapan Mağazalar")
                for mid, madi, mkat in tum_magazalar:
                    if mid in bugun_girenler: st.write(f"• **{madi}** (Kat {mkat})")
            with col2:
                st.error("❌ Henüz Giriş Yapmayan Mağazalar")
                for mid, madi, mkat in tum_magazalar:
                    if mid not in bugun_girenler: st.write(f"• **{madi}** (Kat {mkat})")
                    
        elif secenek == "📸 Kasa Fotoğrafları Denetimi":
            st.header("📸 Mağaza Kasa Fotoğrafları Denetim Ekranı")
            st.write("Mağazaların beyan ettikleri ciroların kasa/Z-raporu fotoğrafları aşağıdadır:")
            
            baglanti, imlec = vt_baglan()
            imlec.execute("""
                SELECT c.tarih, m.adi, c.kdv_dahil, c.kasa_foto 
                FROM gunluk_cirolar c 
                JOIN magazalar m ON c.magaza_id = m.id 
                ORDER BY c.id DESC""")
            veriler = imlec.fetchall()
            baglanti.close()
            
            if len(veriler) == 0:
                st.info("Henüz sisteme yüklenen ciro fotoğrafı bulunmuyor.")
            else:
                for tarih, adi, ciro, foto_blob in veriler:
                    with st.expander(f"📷 {tarih} - {adi} ({ciro} TL)"):
                        if foto_blob:
                            resim = Image.open(io.BytesIO(foto_blob))
                            st.image(resim, caption=f"{adi} Mağazasının Kasa Kanıtı", width=400)
                        else:
                            st.write("Fotoğraf bulunamadı.")
                            
        elif secenek == "⚙️ AVM Yönetim Ayarları":
            st.header("⚙️ AVM Yönetimsel Ayarlar")
            
            # YÖNETİCİ ŞİFRESİ DEĞİŞTİRME BÖLÜMÜ
            st.subheader("🔑 Yönetici Şifresini Değiştir")
            yeni_admin_sifre = st.text_input("Yeni Yönetici Şifresi Belirleyin:", type="password")
            if st.button("Yönetici Şifresini Güncelle"):
                if yeni_admin_sifre.strip() != "":
                    baglanti, imlec = vt_baglan()
                    imlec.execute("UPDATE sistem_ayarlari SET deger = ? WHERE anahtar = 'yonetici_sifre'", (yeni_admin_sifre,))
                    baglanti.commit()
                    baglanti.close()
                    st.success("🎉 Yönetici şifresi başarıyla güncellendi! Bir sonraki girişte geçerli olacaktır.")
                else:
                    st.error("Şifre alanı boş olamaz!")
            
            st.markdown("---")
            st.subheader("➕ Yeni Mağaza Ekle")
            yeni_magaza_adi = st.text_input("Mağaza Adı:")
            yeni_magaza_kat = st.number_input("Bulunduğu Kat:", min_value=-2, max_value=5, value=0, step=1)
            yeni_magaza_sifre = st.text_input("Giriş Şifresi:", value="1234")
            
            if st.button("Mağazayı Sisteme Ekle"):
                if yeni_magaza_adi.strip() != "":
                    baglanti, imlec = vt_baglan()
                    imlec.execute("INSERT INTO magazalar (adi, kat, sifre) VALUES (?, ?, ?)", (yeni_magaza_adi, yeni_magaza_kat, yeni_magaza_sifre))
                    baglanti.commit()
                    baglanti.close()
                    st.success(f"🎉 '{yeni_magaza_adi}' mağazası eklendi!")
                    st.rerun()
                    
            st.markdown("---")
            st.subheader("📋 Mevcut Mağazaları Yönet")
            baglanti, imlec = vt_baglan()
            imlec.execute("SELECT id, adi, kat, sifre FROM magazalar")
            mevcutlar = imlec.fetchall()
            baglanti.close()
            
            for mid, madi, mkat, msifre in mevcutlar:
                sutun_bilgi, sutun_buton = st.columns([4, 1])
                with sutun_bilgi:
                    st.write(f"🏬 **{madi}** (Kat: {mkat}) | 🔑 Şifre: `{msifre}`")
                with sutun_buton:
                    if st.button("Kapat/Sil", key=f"sil_{mid}", type="secondary"):
                        baglanti, imlec = vt_baglan()
                        imlec.execute("DELETE FROM magazalar WHERE id = ?", (mid,))
                        imlec.execute("DELETE FROM gunluk_cirolar WHERE magaza_id = ?", (mid,))
                        baglanti.commit()
                        baglanti.close()
                        st.rerun()