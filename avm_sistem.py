import streamlit as st
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
import datetime
import pandas as pd
from PIL import Image
import io
import hashlib
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from contextlib import contextmanager

st.set_page_config(page_title="AVM Ciro Pro Portal", layout="wide")

# --- 1. JENERATÖR: BAĞLANTI HAVUZU ---
@st.cache_resource
def veritabani_havuzu_olustur():
    baglanti_linki = st.secrets["DATABASE_URL"]
    return ThreadedConnectionPool(1, 10, baglanti_linki)

@contextmanager
def vt_baglan():
    havuz = veritabani_havuzu_olustur()
    baglanti = havuz.getconn()
    try:
        yield baglanti
        baglanti.commit()
    except Exception as e:
        baglanti.rollback()
        raise e
    finally:
        havuz.putconn(baglanti)

# --- 2. KRİPTOGRAFİK ŞİFRELEME ---
def sifre_hashle(sifre):
    return hashlib.sha256(sifre.encode('utf-8')).hexdigest()

# --- 3. KURUMSAL OTOMATİK E-POSTA MOTORU ---
def resmi_haturlatma_mail_at(magaza_adi, alici_email, tarih):
    if "EMAIL_ADRESI" not in st.secrets or "EMAIL_SIFRESI" not in st.secrets:
        return False, "Sistem ayarlarında EMAIL_ADRESI veya EMAIL_SIFRESI eksik!"
        
    gonderen_email = st.secrets["EMAIL_ADRESI"]
    gonderen_sifre = st.secrets["EMAIL_SIFRESI"]
    
    konu = f"⚠️ RESMİ UYARI: Günlük Ciro Raporu Gecikmesi - {tarih}"
    
    icerik = f"""
    Sayın {magaza_adi} Yetkilisi,
    
    {tarih} tarihine ait günlük ciro verilerinizin ve Z-Raporu görselinizin AVM Ciro Pro Portal sistemine henüz girilmediği tespit edilmiştir.
    
    AVM yönetim mevzuatları ve sözleşme maddeleri gereği, günlük ciro girişlerinin her akşam belirlenen saatten önce eksiksiz tamamlanması yasal ve idari bir yükümlülüktür. 
    
    Lütfen bu e-postayı aldıktan sonra aşağıdaki bağlantıyı kullanarak geciken veri girişinizi ivedilikle tamamlayınız.
    
    Sisteme Giriş Adresi: https://avmcirotakip1.streamlit.app
    
    Saygılarımızla,
    AVM Yönetimi Genel Müdürlüğü
    Bilgi Sistemleri ve Denetim Departmanı
    --------------------------------------------------
    Not: Bu e-posta sistem tarafından otomatik olarak üretilmiştir. Ciro girişini bu esnada tamamladıysanız lütfen bu uyarıyı dikkate almayınız.
    """
    
    msg = MIMEMultipart()
    msg['From'] = gonderen_email
    msg['To'] = alici_email
    msg['Subject'] = konu
    msg.attach(MIMEText(icerik, 'plain', 'utf-8'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gonderen_email, gonderen_sifre)
        server.sendmail(gonderen_email, alici_email, msg.as_string())
        server.quit()
        return True, "Başarılı"
    except Exception as e:
        return False, str(e)

# --- 4. VERİTABANI ŞEMA KURULUMU ---
def veritabani_hazirla():
    with vt_baglan() as baglanti:
        imlec = baglanti.cursor()
        imlec.execute("CREATE TABLE IF NOT EXISTS sistem_ayarlari (anahtar TEXT PRIMARY KEY, deger TEXT);")
        varsayilan_super_hash = sifre_hashle("esra123")
        imlec.execute("INSERT INTO sistem_ayarlari (anahtar, deger) VALUES ('super_sifre', %s) ON CONFLICT (anahtar) DO NOTHING;", (varsayilan_super_hash,))
        
        imlec.execute("""
        CREATE TABLE IF NOT EXISTS avm_listesi (
            id SERIAL PRIMARY KEY, avm_adi TEXT UNIQUE, lisans_bitis TEXT,
            odeme_durumu TEXT DEFAULT 'DENEME SÜRESİ', yonetici_sifre TEXT NOT NULL, uyari_saati TEXT DEFAULT '22:00'
        );""")
        imlec.execute("ALTER TABLE avm_listesi ADD COLUMN IF NOT EXISTS uyari_saati TEXT DEFAULT '22:00';")
        
        imlec.execute("""
        CREATE TABLE IF NOT EXISTS magazalar (
            id SERIAL PRIMARY KEY, avm_id INTEGER REFERENCES avm_listesi(id) ON DELETE CASCADE,
            adi TEXT, kat INTEGER, sifre TEXT NOT NULL, eposta TEXT
        );""")
        imlec.execute("ALTER TABLE magazalar ADD COLUMN IF NOT EXISTS eposta TEXT;")
        
        imlec.execute("""
        CREATE TABLE IF NOT EXISTS gunluk_cirolar (
            id SERIAL PRIMARY KEY, avm_id INTEGER REFERENCES avm_listesi(id) ON DELETE CASCADE,
            magaza_id INTEGER REFERENCES magazalar(id) ON DELETE CASCADE, tarih TEXT, 
            kdv_dahil REAL, kdv_haric REAL, kasa_foto BYTEA
        );""")
        
        imlec.execute("""
        CREATE TABLE IF NOT EXISTS aktif_oturumlar (
            token TEXT PRIMARY KEY, kullanici_turu TEXT, avm_id INTEGER, 
            avm_adi TEXT, magaza_id INTEGER, magaza_adi TEXT, olusturma_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""")

veritabani_hazirla()
tarih_bugun = datetime.date.today().strftime("%d-%m-%Y")

# --- 5. OTURUM HAFIZASI VE F5 KONTROLLERİ ---
if "giris_yapildi" not in st.session_state:
    st.session_state.update({
        "giris_yapildi": False, 
        "kullanici_turu": None, 
        "aktif_avm_id": None, 
        "aktif_avm_adi": None, 
        "aktif_magaza_id": None, 
        "aktif_magaza_adi": None
    })

if not st.session_state["giris_yapildi"] and "token" in st.query_params:
    aktif_url_token = st.query_params["token"]
    with vt_baglan() as b:
        imlec = b.cursor()
        imlec.execute("SELECT kullanici_turu, avm_id, avm_adi, magaza_id, magaza_adi FROM aktif_oturumlar WHERE token = %s;", (aktif_url_token,))
        oturum_verisi = imlec.fetchone()
        
    if oturum_verisi:
        st.session_state.update({
            "giris_yapildi": True,
            "kullanici_turu": oturum_verisi[0],
            "aktif_avm_id": oturum_verisi[1],
            "aktif_avm_adi": oturum_verisi[2],
            "aktif_magaza_id": oturum_verisi[3],
            "aktif_magaza_adi": oturum_verisi[4]
        })

def oturum_baslat(kullanici_turu, avm_id=None, avm_adi=None, magaza_id=None, magaza_adi=None):
    yeni_token = str(uuid.uuid4())
    with vt_baglan() as b:
        imlec = b.cursor()
        imlec.execute("""
            INSERT INTO aktif_oturumlar (token, kullanici_turu, avm_id, avm_adi, magaza_id, magaza_adi) 
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (yeni_token, kullanici_turu, avm_id, avm_adi, magaza_id, magaza_adi))
    
    st.query_params["token"] = yeni_token
    st.session_state.update({
        "giris_yapildi": True,
        "kullanici_turu": kullanici_turu,
        "aktif_avm_id": avm_id,
        "aktif_avm_adi": avm_adi,
        "aktif_magaza_id": magaza_id,
        "aktif_magaza_adi": magaza_adi
    })
    st.rerun()

# --- 6. AKILLI VERİ ÖNBELLEKLEME FONKSİYONLARI ---
@st.cache_data
def veri_oku_avm_listesi():
    with vt_baglan() as b:
        imlec = b.cursor()
        imlec.execute("SELECT id, avm_adi, lisans_bitis, odeme_durumu FROM avm_listesi;")
        return imlec.fetchall()

@st.cache_data
def veri_oku_magazalar(avm_id):
    with vt_baglan() as b:
        imlec = b.cursor()
        imlec.execute("SELECT id, adi, kat, eposta FROM magazalar WHERE avm_id = %s ORDER BY adi ASC;", (avm_id,))
        return imlec.fetchall()

@st.cache_data
def veri_oku_grafik_data(a_id, bas_tar, bit_tar):
    if isinstance(bas_tar, (list, tuple)):
        bas_tar = bas_tar[0] if len(bas_tar) > 0 else datetime.date.today()
    if isinstance(bit_tar, (list, tuple)):
        bit_tar = bit_tar[1] if len(bit_tar) == 2 else (bit_tar[0] if len(bit_tar) > 0 else datetime.date.today())

    with vt_baglan() as b:
        query = """
            SELECT c.tarih, m.adi as magaza_adi, m.kat, c.kdv_dahil, c.kdv_haric 
            FROM gunluk_cirolar c 
            JOIN magazalar m ON c.magaza_id = m.id 
            WHERE c.avm_id = %s
        """
        df = pd.read_sql_query(query, b, params=(a_id,))
        
        if not df.empty:
            bas_timestamp = pd.to_datetime(bas_tar)
            bit_timestamp = pd.to_datetime(bit_tar)
            df["tarih_gecici"] = pd.to_datetime(df["tarih"], format="%d-%m-%Y", errors='coerce')
            df = df.dropna(subset=["tarih_gecici"])
            df = df[(df["tarih_gecici"] >= bas_timestamp) & (df["tarih_gecici"] <= bit_timestamp)]
            df = df.drop(columns=["tarih_gecici"])
        return df

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
                imlec = b.cursor()
                imlec.execute("SELECT deger FROM sistem_ayarlari WHERE anahtar = 'super_sifre';")
                guncel_super_sifre = imlec.fetchone()[0]
            if sifre_hashle(super_sifre_input) == guncel_super_sifre:
                oturum_baslat("super")
            else: 
                st.error("❌ Hatalı Şifre!")

    elif tur == "AVM Yönetimi":
        tum_avmler = veri_oku_avm_listesi()
        if tum_avmler:
            avm_sozluk = {a[1]: a[0] for a in tum_avmler}
            secilen_avm_adi = st.selectbox("Yöneticisi Olduğunuz AVM:", list(avm_sozluk.keys()))
            yonetim_sifre = st.text_input("Yönetici Giriş Şifresi:", type="password")
            if st.button("Yönetim Paneline Giriş Yap"):
                with vt_baglan() as b:
                    imlec = b.cursor()
                    imlec.execute("SELECT yonetici_sifre FROM avm_listesi WHERE id = %s;", (avm_sozluk[secilen_avm_adi],))
                    dogru_yonetim_hash = imlec.fetchone()[0]
                if sifre_hashle(yonetim_sifre) == dogru_yonetim_hash:
                    oturum_baslat("yonetim", avm_id=avm_sozluk[secilen_avm_adi], avm_adi=secilen_avm_adi)
                else: 
                    st.error("❌ Hatalı Şifre!")
        else: 
            st.warning("Sistemde henüz kayıtlı AVM bulunmuyor.")
                
    elif tur == "Mağaza Girişi":
        avm_ler = veri_oku_avm_listesi()
        if avm_ler:
            m_avm_sozluk = {a[1]: a[0] for a in avm_ler}
            g_secilen_avm = st.selectbox("Bulunduğunuz AVM:", list(m_avm_sozluk.keys()))
            
            magazalar = veri_oku_magazalar(m_avm_sozluk[g_secilen_avm])
            if magazalar:
                magaza_sozluk = {m[1]: m[0] for m in magazalar}
                secilen_magaza = st.selectbox("Mağazanız:", list(magaza_sozluk.keys()))
                magaza_sifre = st.text_input(f"{secilen_magaza} Şifresi:", type="password")
                if st.button("Mağaza Paneline Giriş Yap"):
                    with vt_baglan() as b:
                        imlec = b.cursor()
                        imlec.execute("SELECT sifre FROM magazalar WHERE id = %s;", (magaza_sozluk[secilen_magaza],))
                        dogru_magaza_hash = imlec.fetchone()[0]
                    if sifre_hashle(magaza_sifre) == dogru_magaza_hash:
                        oturum_baslat("magaza", avm_id=m_avm_sozluk[g_secilen_avm], avm_adi=g_secilen_avm, magaza_id=magaza_sozluk[secilen_magaza], magaza_adi=secilen_magaza)
                    else: 
                        st.error("❌ Hatalı Şifre!")
            else: 
                st.warning("Bu AVM'ye ait mağaza bulunamadı.")

else:
    col_baslik, col_cikis = st.columns([6, 1])
    with col_baslik: st.title("🏢 AVM Ciro Yönetim Portalı")
    with col_cikis:
        if st.button("🚪 Çıkış Yap"):
            if "token" in st.query_params:
                eski_token = st.query_params["token"]
                with vt_baglan() as b:
                    imlec = b.cursor()
                    imlec.execute("DELETE FROM aktif_oturumlar WHERE token = %s;", (eski_token,))
                del st.query_params["token"]
            st.session_state.update({"giris_yapildi": False, "kullanici_turu": None, "aktif_avm_id": None, "aktif_avm_adi": None, "aktif_magaza_id": None, "aktif_magaza_adi": None})
            st.rerun()
    st.markdown("---")

    # --------------------------------------------------------------------------
    # ROLE 1: SÜPER ADMIN PANELİ
    # --------------------------------------------------------------------------
    if st.session_state["kullanici_turu"] == "super":
        st.header("🏢 Süper Admin (Esra) Sağlayıcı Paneli")
        
        raw_avmler = veri_oku_avm_listesi()
        df_avmler = pd.DataFrame(raw_avmler, columns=["AVM ID", "AVM Adı", "Lisans Bitiş", "Ödeme Durumu"])
        st.dataframe(df_avmler, use_container_width=True)
        
        if not df_avmler.empty:
            with st.expander("🗑️ Bir AVM'yi Sistemden Tamamen Kaldır"):
                silinecek_avm_adi = st.selectbox("Sistemden Silinecek AVM:", df_avmler["AVM Adı"].tolist())
                if st.button("🔴 Seçilen AVM'yi SİL", type="primary"):
                    with vt_baglan() as b:
                        imlec = b.cursor()
                        imlec.execute("DELETE FROM avm_listesi WHERE avm_adi = %s;", (silinecek_avm_adi,))
                    st.cache_data.clear()
                    st.success(f"'{silinecek_avm_adi}' silindi.")
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
                        imlec = b.cursor()
                        imlec.execute("INSERT INTO avm_listesi (avm_adi, lisans_bitis, odeme_durumu, yonetici_sifre) VALUES (%s, %s, %s, %s);", (yeni_avm_adi, yeni_avm_lisans.strftime("%Y-%m-%d"), yeni_avm_odeme, sifre_hashle(yeni_avm_admin_sifre)))
                    st.cache_data.clear()
                    st.success(f"🎉 '{yeni_avm_adi}' oluşturuldu!")
                    st.rerun()
                except Exception as e: 
                    st.error(f"Veritabanı Hatası: {e}")

    # --------------------------------------------------------------------------
    # ROLE 2: AVM YÖNETİCİ PANELİ
    # --------------------------------------------------------------------------
    elif st.session_state["kullanici_turu"] == "yonetim":
        a_id = st.session_state["aktif_avm_id"]
        a_adi = st.session_state["aktif_avm_adi"]
        
        with vt_baglan() as b:
            imlec = b.cursor()
            imlec.execute("SELECT lisans_bitis, odeme_durumu FROM avm_listesi WHERE id = %s;", (a_id,))
            bitis_str, odeme_durumu = imlec.fetchone()
        
        bitis_tarihi = datetime.datetime.strptime(bitis_str, "%Y-%m-%d").date()
        kalan_gun = (bitis_tarihi - datetime.date.today()).days
        
        if kalan_gun < 0:
            st.error(f"🚨 **ERİŞİM ENGELLENDİ:** Lisans doldu!")
            st.stop()

        secenek = st.sidebar.radio("Yönetim Menüsü:", ["📊 Raporlar & Grafikler", "📸 Kasa Fotoğrafları", "⚙️ Mağaza ve Şifre Ayarları"])
        
        if secenek == "📊 Raporlar & Grafikler":
            st.header(f"📊 {a_adi} Yönetim Kontrol Paneli")
            
            t_magazalar = veri_oku_magazalar(a_id)
            with vt_baglan() as b:
                imlec = b.cursor()
                imlec.execute("SELECT magaza_id FROM gunluk_cirolar WHERE avm_id = %s AND tarih = %s;", (a_id, tarih_bugun))
                g_magaza_ids = [r[0] for r in imlec.fetchall()]
            
            if t_magazalar:
                gonderen_listesi = [m[1] for m in t_magazalar if m[0] in g_magaza_ids]
                gondermeyen_listesi = [{"id": m[0], "adi": m[1], "eposta": m[3] if len(m)>3 and m[3] else ""} for m in t_magazalar if m[0] not in g_magaza_ids]
                
                m_col1, m_col2, m_col3 = st.columns(3)
                with m_col1: st.metric("Toplam Mağaza", len(t_magazalar))
                with m_col2: st.metric("Bugün Ciro Girenler", len(gonderen_listesi))
                with m_col3: st.metric("Rapor Beklenenler", len(gondermeyen_listesi))
                
                if gondermeyen_listesi:
                    st.markdown("---")
                    st.subheader("✉️ Bugün Ciro Girmeyen Mağazalar ve Resmi Hatırlatma")
                    st.caption("Aşağıdaki listeden ciro girmeyen mağazalara tek tıkla resmi ihtar/hatırlatma e-postası gönderebilirsiniz.")
                    
                    for eksik in gondermeyen_listesi:
                        c_m_adi, c_m_eposta = eksik["adi"], eksik["eposta"]
                        col_m_adi, col_m_mail, col_m_aksiyon = st.columns([3, 3, 2])
                        
                        with col_m_adi:
                            st.write(f"• **{c_m_adi}**")
                        with col_m_mail:
                            st.write(f"*{c_m_eposta if c_m_eposta else 'E-posta adresi girilmemiş!'}*")
                        with col_m_aksiyon:
                            if c_m_eposta:
                                if st.button(f"⚠️ Mail Gönder", key=f"btn_mail_{eksik['id']}"):
                                    with st.spinner("Resmi e-posta gönderiliyor..."):
                                        durum, mesaj = resmi_haturlatma_mail_at(c_m_adi, c_m_eposta, tarih_bugun)
                                        if durum:
                                            st.toast(f"✓ {c_m_adi} için hatırlatma e-postası başarıyla gönderildi!", icon="✉️")
                                        else:
                                            st.error(f"Hata: {mesaj}")
                            else:
                                st.button("⚠️ Mail Gönder", key=f"btn_mail_{eksik['id']}", disabled=True)
                
                st.markdown("---")
                st.subheader("🔍 Tarih Aralıklı Gelişmiş Analiz Filtreleri")
                f_col1, f_col2, f_col3 = st.columns(3)
                with f_col1:
                    bugun_dt = datetime.date.today()
                    tarih_araligi = st.date_input("Analiz Tarih Aralığı Seçin:", [bugun_dt.replace(day=1), bugun_dt])
                
                magaza_df_all = pd.DataFrame(t_magazalar, columns=["id", "adi", "kat", "eposta"])
                with f_col2:
                    secilen_magazalar = st.multiselect("Mağaza Filtresi:", ["Tüm Mağazalar"] + magaza_df_all["adi"].tolist(), default="Tüm Mağazalar")
                with f_col3:
                    secilen_kat = st.selectbox("Kat Filtresi:", ["Tüm Katlar"] + sorted(list(magaza_df_all["kat"].unique())))

                if isinstance(tarih_araligi, (list, tuple)) and len(tarih_araligi) == 2:
                    bas_tar, bit_tar = tarih_araligi
                elif isinstance(tarih_araligi, (list, tuple)) and len(tarih_araligi) == 1:
                    bas_tar = bit_tar = tarih_araligi[0]
                else:
                    bas_tar = bit_tar = tarih_araligi

                df_analiz = veri_oku_grafik_data(a_id, bas_tar, bit_tar).copy()

                if not df_analiz.empty:
                    if "Tüm Mağazalar" not in secilen_magazalar and secilen_magazalar:
                        df_analiz = df_analiz[df_analiz["magaza_adi"].isin(secilen_magazalar)]
                    if secilen_kat != "Tüm Katlar":
                        df_analiz = df_analiz[df_analiz["kat"] == int(secilen_kat)]

                    if not df_analiz.empty:
                        df_analiz["tarih_dt"] = pd.to_datetime(df_analiz["tarih"], format="%d-%m-%Y", errors='coerce')
                        df_analiz = df_analiz.dropna(subset=["tarih_dt"]).sort_values("tarih_dt")

                        kpi1, kpi2, kpi3 = st.columns(3)
                        with kpi1: st.metric("Toplam Ciro (KDV Dahil)", f"{df_analiz['kdv_dahil'].sum():,.2f} TL")
                        with kpi2: st.metric("Toplam Ciro (KDV Hariç)", f"{df_analiz['kdv_haric'].sum():,.2f} TL")
                        with kpi3:
                            ml = df_analiz.groupby("magaza_adi")["kdv_dahil"].sum()
                            st.metric("Dönem Lideri", ml.idxmax() if not ml.empty else "Veri Yok")

                        tab_trend, tab_kiyas, tab_tablo = st.tabs(["📈 Trend Çizgisi", "📊 Mağaza Dağılımı", "📋 Detaylı Tablo"])
                        with tab_trend:
                            st.line_chart(df_analiz.pivot_table(index="tarih_dt", columns="magaza_adi", values="kdv_dahil", aggfunc="sum").fillna(0))
                        with tab_kiyas:
                            st.bar_chart(data=df_analiz.groupby("magaza_adi")["kdv_dahil"].sum().reset_index(), x="magaza_adi", y="kdv_dahil")
                        with tab_tablo:
                            st.dataframe(df_analiz[["tarih", "magaza_adi", "kat", "kdv_dahil", "kdv_haric"]], use_container_width=True)
                    else: 
                        st.info("Uygun ciro verisi bulunamadı.")
                else: 
                    st.info("Seçilen tarih aralığında ciro kaydı yok.")
            else: 
                st.warning("Henüz mağaza yok.")

        elif secenek == "📸 Kasa Fotoğrafları":
            st.header("📸 Z-Raporu Denetimi")
            with vt_baglan() as b:
                imlec = b.cursor()
                imlec.execute("SELECT c.tarih, m.adi, c.kdv_dahil, c.kasa_foto FROM gunluk_cirolar c JOIN magazalar m ON c.magaza_id = m.id WHERE c.avm_id = %s ORDER BY c.id DESC;", (a_id,))
                veriler = imlec.fetchall()
            for tarih, adi, ciro, foto_blob in veriler:
                with st.expander(f"📷 {tarih} - {adi} ({ciro} TL)"):
                    if foto_blob: 
                        st.image(Image.open(io.BytesIO(bytes(foto_blob))), width=400)

        elif secenek == "⚙️ Mağaza ve Şifre Ayarları":
            st.header("⚙️ Mağaza Yönetim Alanı")
            
            # 🔄 YENİ BÖLÜM: MEVCUT MAĞAZALARIN BİLGİLERİNİ GÜNCELLEME (E-POSTA SONRADAN EKLEME)
            with st.expander("📝 Kayıtlı Mağaza Bilgilerini Güncelle (E-posta Ekleme / Değiştirme)"):
                mevcut_m_listesi = veri_oku_magazalar(a_id)
                if mevcut_m_listesi:
                    m_guncel_sozluk = {m[1]: {"id": m[0], "kat": m[1], "eposta": m[3] if len(m)>3 and m[3] else ""} for m in mevcut_m_listesi}
                    secilen_guncel_m = st.selectbox("Bilgileri Güncellenecek Mağaza:", list(m_guncel_sozluk.keys()))
                    
                    eski_veri = m_guncel_sozluk[secilen_guncel_m]
                    guncel_eposta_input = st.text_input("E-Posta Adresi:", value=eski_veri["eposta"])
                    
                    if st.button("🔄 Bilgileri Güncelle"):
                        with vt_baglan() as b:
                            imlec = b.cursor()
                            imlec.execute("UPDATE magazalar SET eposta = %s WHERE id = %s;", (guncel_eposta_input.strip() if guncel_eposta_input else None, eski_veri["id"]))
                        st.cache_data.clear()
                        st.success(f"✓ '{secilen_guncel_m}' e-posta adresi başarıyla güncellendi!")
                        st.rerun()
                else:
                    st.info("Sistemde güncellenecek mağaza bulunmuyor.")

            with st.expander("📥 Excel Dosyasından Toplu Mağaza Yükle"):
                st.markdown("**Şablon Sütunları:** `Mağaza Adı` | `Kat` | `Giriş Şifresi` | `E-Posta`")
                yuklenen_excel = st.file_uploader("Excel Dosyası Seçin (.xlsx)", type=["xlsx"])
                if yuklenen_excel is not None:
                    try:
                        df_ex = pd.read_excel(yuklenen_excel)
                        df_ex.columns = [col.strip() for col in df_ex.columns]
                        
                        if all(col in df_ex.columns for col in ["Mağaza Adı", "Kat", "Giriş Şifresi", "E-Posta"]):
                            if st.button("🚀 Excel'den Aktar"):
                                with vt_baglan() as b:
                                    imlec = b.cursor()
                                    for _, satir in df_ex.iterrows():
                                        m_adi = str(satir["Mağaza Adı"]).strip()
                                        m_eposta = str(satir["E-Posta"]).strip() if "E-Posta" in df_ex.columns and pd.notna(satir["E-Posta"]) else None
                                        if m_adi and m_adi != "nan":
                                            try:
                                                kat_no = int(satir["Kat"])
                                            except:
                                                kat_no = 0
                                            sifre_str = str(satir["Giriş Şifresi"]).strip().split('.')[0]
                                            imlec.execute("INSERT INTO magazalar (avm_id, adi, kat, sifre, eposta) VALUES (%s, %s, %s, %s, %s);", 
                                                           (a_id, m_adi, kat_no, sifre_hashle(sifre_str), m_eposta))
                                st.cache_data.clear()
                                st.success("Mağazalar e-posta adresleriyle birlikte başarıyla aktarıldı.")
                                st.rerun()
                        else: 
                            st.error("Excel sütun isimleri hatalı! Lütfen 'E-Posta' sütununun bulunduğundan emin olun.")
                    except Exception as e: 
                        st.error(f"Hata oluştu: {e}")

            with st.expander("➕ Tek Tek Yeni Mağaza Ekle"):
                yeni_m_adi = st.text_input("Mağaza Adı:")
                yeni_m_kat = st.number_input("Kat:", min_value=-2, max_value=5, value=0)
                yeni_m_eposta = st.text_input("Mağaza Resmi E-Posta Adresi:")
                yeni_m_sifre = st.text_input("Mağaza Şifresi:", value="1234")
                if st.button("Mağazayı Kaydet"):
                    if yeni_m_adi.strip() != "":
                        with vt_baglan() as b:
                            imlec = b.cursor()
                            imlec.execute("INSERT INTO magazalar (avm_id, adi, kat, sifre, eposta) VALUES (%s, %s, %s, %s, %s);", (a_id, yeni_m_adi, yeni_m_kat, sifre_hashle(yeni_m_sifre), yeni_m_eposta.strip() if yeni_m_eposta else None))
                        st.cache_data.clear()
                        st.success(f"✓ {yeni_m_adi} e-posta adresiyle eklendi.")
                        st.rerun()
            
            with st.expander("🗑️ Mağaza Sil"):
                mevcut_magazalar = veri_oku_magazalar(a_id)
                if mevcut_magazalar:
                    m_sil_sozluk = {m[1]: m[0] for m in mevcut_magazalar}
                    silinecek_m_adi = st.selectbox("Silinecek Mağaza:", list(m_sil_sozluk.keys()))
                    if st.button("🔴 Mağazayı Sil", type="primary"):
                        with vt_baglan() as b:
                            imlec = b.cursor()
                            imlec.execute("DELETE FROM magazalar WHERE id = %s;", (m_sil_sozluk[silinecek_m_adi],))
                        st.cache_data.clear()
                        st.success(f"'{silinecek_m_adi}' silindi.")
                        st.rerun()

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
            secilen_rapor_tarihi = st.date_input("Rapor Tarihi:", datetime.date.today())
            tarih_formatli = secilen_rapor_tarihi.strftime("%d-%m-%Y")
            
            with vt_baglan() as b:
                imlec = b.cursor()
                imlec.execute("SELECT COUNT(*) FROM gunluk_cirolar WHERE magaza_id = %s AND tarih = %s;", (m_id, tarih_formatli))
                secilen_tarih_var_mi = imlec.fetchone()[0]
            
            if secilen_tarih_var_mi > 0: 
                st.success(f"🎉 {tarih_formatli} ciro girişiniz bulutta kayıtlıdır.")
            else:
                kdv_dahil = st.number_input("KDV Dahil Ciro:", min_value=0.0, step=100.0)
                kdv_haric = st.number_input("KDV Hariç Ciro:", min_value=0.0, step=100.0)
                yuklenen_dosya = st.file_uploader("📸 Z-Raporu Fotoğrafı:", type=["png", "jpg", "jpeg"])
                
                if st.button("Ciroyu Gönder"):
                    if yuklenen_dosya is not None:
                        foto_byte = yuklenen_dosya.read()
                        with vt_baglan() as b:
                            imlec = b.cursor()
                            imlec.execute("INSERT INTO gunluk_cirolar (avm_id, magaza_id, tarih, kdv_dahil, kdv_haric, kasa_foto) VALUES (%s, %s, %s, %s, %s, %s);", (a_id, m_id, tarih_formatli, kdv_dahil, kdv_haric, psycopg2.Binary(foto_byte)))
                        st.cache_data.clear()
                        st.success(f"🎉 Başarıyla buluta işlendi!")
                        st.rerun()
                    else: 
                        st.error("Lütfen z-raporu fotoğrafını sisteme yükleyin!")
                        
        with sekme_rapor:
            with vt_baglan() as b:
                df_magaza_ozel = pd.read_sql_query("SELECT tarih, kdv_dahil, kdv_haric FROM gunluk_cirolar WHERE magaza_id = %s ORDER BY id DESC", b, params=(m_id,))
            if not df_magaza_ozel.empty: 
                st.dataframe(df_magaza_ozel, use_container_width=True)
