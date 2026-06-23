import streamlit as st
import sqlite3
import datetime
import pandas as pd
from PIL import Image
import io

st.set_page_config(page_title="AVM Ciro Pro Portal", layout="wide")

# --- 1. GÜVENLİ VERİTABANI BAĞLANTISI (Kilitlenmeleri Önler) ---
def vt_baglan():
    return sqlite3.connect("avm_veritabani.db", timeout=20)

# --- 2. SİSTEMİ BAŞLAT VE TABLOLARI OLUŞTUR ---
def veritabani_hazirla():
    with vt_baglan() as baglanti:
        imlec = baglanti.cursor()
        
        # Mağazalar Tablosu
        imlec.execute("""
        CREATE TABLE IF NOT EXISTS magazalar (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            adi TEXT, 
            kat INTEGER,
            sifre TEXT DEFAULT '1234'
        )""")

        # Günlük Cirolar Tablosu (Fotoğraf BLOB olarak tutulur)
        imlec.execute("""
        CREATE TABLE IF NOT EXISTS gunluk_cirolar (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            magaza_id INTEGER, 
            tarih TEXT, 
            kdv_dahil REAL, 
            kdv_haric REAL,
            kasa_foto BLOB
        )""")

        # Sistem Ayarları Tablosu
        imlec.execute("CREATE TABLE IF NOT EXISTS sistem_ayarlari (anahtar TEXT PRIMARY KEY, deger TEXT)")
        imlec.execute("INSERT OR IGNORE INTO sistem_ayarlari (anahtar, deger) VALUES ('yonetici_sifre', 'admin123')")
        imlec.execute("INSERT OR IGNORE INTO sistem_ayarlari (anahtar, deger) VALUES ('super_sifre', 'esra123')")

        # Süper Admin İçin Çoklu AVM Takip Tablosu
        imlec.execute("""
        CREATE TABLE IF NOT EXISTS avm_listesi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            avm_adi TEXT,
            lisans_bitis TEXT,
            odeme_durumu TEXT DEFAULT 'DENEME SÜRESİ'
        )""")

        # Eğer sistemde hiç AVM yoksa varsayılan ilk AVM'yi (14 günlük deneme süresiyle) ekle
        imlec.execute("SELECT COUNT(*) FROM avm_listesi")
        if imlec.fetchone()[0] == 0:
            varsayilan_bitis = (datetime.date.today() + datetime.timedelta(days=14)).strftime("%Y-%m-%d")
            imlec.execute("INSERT INTO avm_listesi (avm_adi, lisans_bitis, odeme_durumu) VALUES (?, ?, ?)", 
                          ("Merkez Pro AVM", varsayilan_bitis, "DENEME SÜRESİ"))

        # Eğer hiç mağaza yoksa varsayılan mağazaları yükle
        imlec.execute("SELECT COUNT(*) FROM magazalar")
        if imlec.fetchone()[0] == 0:
            varsayilan_magazalar = [("Zara", 1, "zara123"), ("LC Waikiki", 1, "lcw123"), ("Starbucks", 0, "sbux123"), ("Teknosa", 2, "tekno123")]
            imlec.executemany("INSERT INTO magazalar (adi, kat, sifre) VALUES (?, ?, ?)", varsayilan_magazalar)
            
        baglanti.commit()

veritabani_hazirla()

# --- 3. OTURUM HAFIZASI KONTROLLERİ ---
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
    
    tur = st.selectbox("Kullanıcı Türü:", ["Mağaza Girişi", "AVM Yönetimi", "Süper Admin (Esra)"])
    
    # SÜPER ADMIN GİRİŞİ
    if tur == "Süper Admin (Esra)":
        super_sifre_input = st.text_input("Süper Admin Giriş Şifresi:", type="password")
        if st.button("Süper Yönetim Paneline Giriş Yap"):
            with vt_baglan() as b:
                guncel_super_sifre = b.cursor().execute("SELECT deger FROM sistem_ayarlari WHERE anahtar = 'super_sifre'").fetchone()[0]
            
            if super_sifre_input == guncel_super_sifre:
                st.session_state["giris_yapildi"] = True
                st.session_state["kullanici_turu"] = "super"
                st.success("Esra Sistem Sağlayıcı girişi başarılı!")
                st.rerun()
            else:
                st.error("❌ Hatalı Süper Admin Şifresi!")

    # AVM YÖNETİMİ GİRİŞİ
    elif tur == "AVM Yönetimi":
        yonetim_sifre = st.text_input("Yönetici Giriş Şifresi:", type="password")
        if st.button("Yönetim Paneline Giriş Yap"):
            with vt_baglan() as b:
                guncel_admin_sifre = b.cursor().execute("SELECT deger FROM sistem_ayarlari WHERE anahtar = 'yonetici_sifre'").fetchone()[0]
            
            if yonetim_sifre == guncel_admin_sifre:
                st.session_state["giris_yapildi"] = True
                st.session_state["kullanici_turu"] = "yonetim"
                st.success("Yönetim girişi başarılı!")
                st.rerun()
            else:
                st.error("❌ Hatalı Yönetici Şifresi!")
                
    # MAĞAZA GİRİŞİ
    elif tur == "Mağaza Girişi":
        with vt_baglan() as b:
            magazalar = b.cursor().execute("SELECT id, adi FROM magazalar").fetchall()
        
        if len(magazalar) == 0:
            st.warning("Sistemde kayıtlı mağaza bulunamadı.")
        else:
            magaza_sozluk = {m[1]: m[0] for m in magazalar}
            secilen_magaza = st.selectbox("Mağazanız:", list(magaza_sozluk.keys()))
            magaza_sifre = st.text_input(f"{secilen_magaza} Mağaza Şifresi:", type="password")
            
            if st.button("Mağaza Paneline Giriş Yap"):
                with vt_baglan() as b:
                    dogru_sifre = b.cursor().execute("SELECT sifre FROM magazalar WHERE id = ?", (magaza_sozluk[secilen_magaza],)).fetchone()[0]
                
                if magaza_sifre == dogru_sifre:
                    st.session_state["giris_yapildi"] = True
                    st.session_state["kullanici_turu"] = "magaza"
                    st.session_state["aktif_magaza_id"] = magaza_sozluk[secilen_magaza]
                    st.session_state["aktif_magaza_adi"] = secilen_magaza
                    st.rerun()
                else:
                    st.error("❌ Hatalı Mağaza Şifresi!")

# ==============================================================================
# SİSTEM İÇİ (Giriş Sonrası Yönetim Alanları)
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

    # --------------------------------------------------------------------------
    # ROLE 1: SÜPER ADMIN PANELİ (Esra'nın Özel Ekranı)
    # --------------------------------------------------------------------------
    if st.session_state["kullanici_turu"] == "super":
        st.header("🏢 Süper Admin (Esra) Sağlayıcı Paneli")
        st.write("Sistemi kullanan AVM'leri, lisans sürelerini ve ödeme durumlarını buradan kontrol edebilirsiniz.")
        
        # SÜPER ADMIN ŞİFRE DEĞİŞTİRME BÖLÜMÜ (Yeni Eklenen Kısım)
        with st.expander("🔑 Süper Admin Şifremi Değiştir"):
            yeni_super_sifre = st.text_input("Yeni Süper Admin Şifresi Belirleyin:", type="password")
            if st.button("Süper Şifreyi Güncelle"):
                if yeni_super_sifre.strip() != "":
                    with vt_baglan() as b:
                        b.cursor().execute("UPDATE sistem_ayarlari SET deger = ? WHERE anahtar = 'super_sifre'", (yeni_super_sifre,))
                        b.commit()
                    st.success("🎉 Süper Admin giriş şifreniz başarıyla güncellendi! Bir sonraki girişte geçerli olacaktır.")
                    st.rerun()
                else:
                    st.error("Şifre alanı boş bırakılamaz!")

        st.markdown("---")
        
        # Mevcut AVM Listesini Göster
        st.subheader("📋 Yayındaki AVM'ler ve Lisans Durumları")
        with vt_baglan() as b:
            df_avmler = pd.read_sql_query("SELECT id as [AVM ID], avm_adi as [AVM Adı], lisans_bitis as [Lisans Bitiş Tarihi], odeme_durumu as [Ödeme Durumu] FROM avm_listesi", b)
        st.dataframe(df_avmler, use_container_width=True)
        
        # Yeni AVM Tanımlama Ekranı
        st.markdown("---")
        st.subheader("➕ Yeni Müşteri / AVM Ekle")
        c1, c2, c3 = st.columns(3)
        with c1:
            yeni_avm_adi = st.text_input("Müşteri AVM Adı:")
        with c2:
            yeni_avm_lisans = st.date_input("Lisans Bitiş Tarihi (Deneme için bugünden itibaren 14 gün seçebilirsiniz):", datetime.date.today() + datetime.timedelta(days=14))
        with c3:
            yeni_avm_odeme = st.selectbox("Ödeme/Hesap Durumu:", ["DENEME SÜRESİ", "ÖDENDİ", "BEKLİYOR"])
            
        if st.button("🚀 Yeni AVM'yi Sisteme Tanımla"):
            if yeni_avm_adi.strip() != "":
                with vt_baglan() as b:
                    b.cursor().execute("INSERT INTO avm_listesi (avm_adi, lisans_bitis, odeme_durumu) VALUES (?, ?, ?)", 
                                  (yeni_avm_adi, yeni_avm_lisans.strftime("%Y-%m-%d"), yeni_avm_odeme))
                    b.commit()
                st.success(f"🎉 '{yeni_avm_adi}' sisteme başarıyla kaydedildi!")
                st.rerun()
            else:
                st.error("Lütfen geçerli bir AVM adı giriniz.")
                
        # AVM Lisans Düzenleme / Silme Alanı
        st.markdown("---")
        st.subheader("⚙️ AVM Yönetimsel İşlemler (Lisans Uzatma / Silme)")
        with vt_baglan() as b:
            avm_secenekleri = b.cursor().execute("SELECT id, avm_adi FROM avm_listesi").fetchall()
            
        if avm_secenekleri:
            avm_dict = {a[1]: a[0] for a in avm_secenekleri}
            secilen_yonetim_avm = st.selectbox("İşlem Yapılacak AVM Seçin:", list(avm_dict.keys()))
            
            col_uzat, col_sil = st.columns(2)
            with col_uzat:
                yeni_durum_sec = st.selectbox("Ödeme Durumunu Güncelle:", ["ÖDENDİ", "BEKLİYOR", "DENEME SÜRESİ"], key="durum_guncel")
                yeni_tarih_sec = st.date_input("Lisans Tarihini Güncelle/Uzat:", datetime.date.today() + datetime.timedelta(days=365))
                if st.button("🔄 Bilgileri ve Süreyi Güncelle"):
                    with vt_baglan() as b:
                        b.cursor().execute("UPDATE avm_listesi SET lisans_bitis = ?, odeme_durumu = ? WHERE id = ?", 
                                      (yeni_tarih_sec.strftime("%Y-%m-%d"), yeni_durum_sec, avm_dict[secilen_yonetim_avm]))
                        b.commit()
                    st.success(f"✓ {secilen_yonetim_avm} lisans bilgileri güncellendi!")
                    st.rerun()
            with col_sil:
                st.warning("⚠️ Aşağıdaki buton seçili AVM'yi sistemden tamamen kaldırır.")
                if st.button("❌ AVM'yi Tamamen Sil", type="secondary"):
                    with vt_baglan() as b:
                        b.cursor().execute("DELETE FROM avm_listesi WHERE id = ?", (avm_dict[secilen_yonetim_avm],))
                        b.commit()
                    st.error(f"'{secilen_yonetim_avm}' sistemden silindi.")
                    st.rerun()

    # --------------------------------------------------------------------------
    # ROLE 2: AVM YÖNETİCİ PANELİ (Lisans Kontrol Mekanizmalı)
    # --------------------------------------------------------------------------
    elif st.session_state["kullanici_turu"] == "yonetim":
        # --- LİSANS VE 14 GÜNLÜK DENEME SÜRESİ KONTROLÜ ---
        with vt_baglan() as b:
            lisans_bilgisi = b.cursor().execute("SELECT avm_adi, lisans_bitis, odeme_durumu FROM avm_listesi ORDER BY id ASC LIMIT 1").fetchone()
            
        if lisans_bilgisi:
            avm_adi_kayit, bitis_tarihi_str, odeme_durumu_kayit = lisans_bilgisi
            bitis_tarihi = datetime.datetime.strptime(bitis_tarihi_str, "%Y-%m-%d").date()
            bugun_tarih = datetime.date.today()
            kalan_gun = (bitis_tarihi - bugun_tarih).days
            
            # 1. Senaryo: Lisans Tamamen Bitmiş (Sistemi Kilitle)
            if kalan_gun < 0:
                st.error(f"🚨 **ERİŞİM ENGELENDİ:** {avm_adi_kayit} yönetim lisans/deneme süreniz dolmuştur! Portala erişim sağlamak için lütfen Sistem Sağlayıcınız (Esra) ile iletişime geçip ödemenizi tamamlayın.")
                st.info(f"📋 **Mevcut Durum:** Son Bitiş Tarihi: {bitis_tarihi_str} | Ödeme Durumu: {odeme_durumu_kayit}")
                st.stop()
                
            # 2. Senaryo: Deneme veya Normal Lisans Süresinin Bitimine 14 Gün veya Daha Az Kalmış (Uyarı Göster)
            elif kalan_gun <= 14:
                st.warning(f"⚠️ **ÖNEMLİ LİSANS UYARISI:** {avm_adi_kayit} için kullanım sürenizin/deneme periyodunuzun bitmesine son **{kalan_gun} gün** kaldı! Sistem kapanmadan önce ödemenizi gerçekleştirmeniz gerekmektedir. (Ödeme Durumunuz: {odeme_durumu_kayit})")
            else:
                st.info(f"🟢 **Lisans Aktif:** {avm_adi_kayit} lisans güvenli kullanım süresi devam ediyor. Kalan gün sayınız: {kalan_gun}")
        else:
            st.error("Sistemde aktif bir AVM lisans kaydı bulunamadı. Lütfen Süper Admin ile görüşün.")
            st.stop()

        # LİSANS KONTROLÜ GEÇİLDİYSE ESKİ PANEL AYNAYEN ÇALIŞIR:
        secenek = st.sidebar.radio("Yönetim Menüsü:", ["📊 Genel Raporlar & Grafikler", "📸 Kasa Fotoğrafları Denetimi", "⚙️ AVM Yönetim Ayarları"])
        
        if secenek == "📊 Genel Raporlar & Grafikler":
            st.header(f"📊 AVM Yönetim Raporları Paneli")
            
            with vt_baglan() as b:
                df_cirolar = pd.read_sql_query("""
                    SELECT c.tarih, m.adi as magaza_adi, m.kat, c.kdv_dahil, c.kdv_haric 
                    FROM gunluk_cirolar c 
                    JOIN magazalar m ON c.magaza_id = m.id
                """, b)
                
                tum_magazalar = b.cursor().execute("SELECT id, adi, kat FROM magazalar").fetchall()
                bugun_girenler = [satir[0] for satir in b.cursor().execute("SELECT magaza_id FROM gunluk_cirolar WHERE tarih = ?", (tarih_bugun,)).fetchall()]
            
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
            
            with vt_baglan() as b:
                veriler = b.cursor().execute("""
                    SELECT c.tarih, m.adi, c.kdv_dahil, c.kasa_foto 
                    FROM gunluk_cirolar c 
                    JOIN magazalar m ON c.magaza_id = m.id 
                    ORDER BY c.id DESC""").fetchall()
            
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
            
            st.subheader("🔑 Yönetici Şifresini Değiştir")
            yeni_admin_sifre = st.text_input("Yeni Yönetici Şifresi Belirleyin:", type="password")
            if st.button("Yönetici Şifresini Güncelle"):
                if yeni_admin_sifre.strip() != "":
                    with vt_baglan() as b:
                        b.cursor().execute("UPDATE sistem_ayarlari SET deger = ? WHERE anahtar = 'yonetici_sifre'", (yeni_admin_sifre,))
                        b.commit()
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
                    with vt_baglan() as b:
                        b.cursor().execute("INSERT INTO magazalar (adi, kat, sifre) VALUES (?, ?, ?)", (yeni_magaza_adi, yeni_magaza_kat, yeni_magaza_sifre))
                        b.commit()
                    st.success(f"🎉 '{yeni_magaza_adi}' mağazası eklendi!")
                    st.rerun()
                    
            st.markdown("---")
            st.subheader("📋 Mevcut Mağazaları Yönet")
            with vt_baglan() as b:
                mevcutlar = b.cursor().execute("SELECT id, adi, kat, sifre FROM magazalar").fetchall()
            
            for mid, madi, mkat, msifre in mevcutlar:
                sutun_bilgi, sutun_buton = st.columns([4, 1])
                with sutun_bilgi:
                    st.write(f"🏬 **{madi}** (Kat: {mkat}) | 🔑 Şifre: `{msifre}`")
                with sutun_buton:
                    if st.button("Kapat/Sil", key=f"sil_{mid}", type="secondary"):
                        with vt_baglan() as b:
                            b.cursor().execute("DELETE FROM magazalar WHERE id = ?", (mid,))
                            b.cursor().execute("DELETE FROM gunluk_cirolar WHERE magaza_id = ?", (mid,))
                            b.commit()
                        st.rerun()

    # --------------------------------------------------------------------------
    # ROLE 3: MAĞAZA KULLANICISI PANELİ (Eski Kod Değişmedi)
    # --------------------------------------------------------------------------
    elif st.session_state["kullanici_turu"] == "magaza":
        m_id = st.session_state["aktif_magaza_id"]
        m_adi = st.session_state["aktif_magaza_adi"]
        
        sekme_giris, sekme_rapor = st.tabs(["💰 Günlük Ciro Girişi", "📅 Mağaza Geçmiş Raporları"])
        
        with sekme_giris:
            st.header(f"🛍️ {m_adi} Veri Giriş Ekranı")
            
            with st.expander("🔑 Giriş Şifremi Değiştir"):
                yeni_sifre = st.text_input("Yeni Şifre:", type="password")
                if st.button("Şifremi Güncelle"):
                    if yeni_sifre.strip() != "":
                        with vt_baglan() as b:
                            b.cursor().execute("UPDATE magazalar SET sifre = ? WHERE id = ?", (yeni_sifre, m_id))
                            b.commit()
                        st.success("🎉 Şifreniz başarıyla değiştirildi!")
                    else:
                        st.error("Şifre alanı boş bırakılamaz!")
            
            st.markdown("---")
            
            with vt_baglan() as b:
                giris_var_mi = b.cursor().execute("SELECT COUNT(*) FROM gunluk_cirolar WHERE magaza_id = ? AND tarih = ?", (m_id, tarih_bugun)).fetchone()[0]
            
            if giris_var_mi > 0:
                st.success(f"🎉 Harika! {m_adi} için bugün ({tarih_bugun}) ciro girişi zaten tamamlanmış.")
            else:
                st.warning("⚠️ Bugünün ciro verisi henüz sisteme girilmemiş.")
                
                kdv_dahil = st.number_input("KDV Dahil Toplam Ciro (TL):", min_value=0.0, step=500.0)
                kdv_haric = st.number_input("KDV Hariç Net Ciro (TL):", min_value=0.0, step=500.0)
                
                yuklenen_dosya = st.file_uploader("📸 Kasa Raporu / Z-Raporu Fotoğrafı Yükleyin (Zorunlu):", type=["png", "jpg", "jpeg"])
                
                if st.button("Ciro Verisini ve Fotoğrafı Güvenli Gönder"):
                    if yuklenen_dosya is not None:
                        foto_byte = yuklenen_dosya.read()
                        
                        with vt_baglan() as b:
                            b.cursor().execute("""
                                INSERT INTO gunluk_cirolar (magaza_id, tarih, kdv_dahil, kdv_haric, kasa_foto) 
                                VALUES (?, ?, ?, ?, ?)""", 
                                (m_id, tarih_bugun, kdv_dahil, kdv_haric, foto_byte))
                            b.commit()
                        st.success("✓ Ciro verisi ve kasa fotoğrafı başarıyla veritabanına kilitlendi!")
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
            else:
                st.info("Henüz geçmiş günlere ait bir ciro veriniz bulunmuyor.")
