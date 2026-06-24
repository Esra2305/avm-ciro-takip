import streamlit as st
import psycopg2  # Bulut veritabanı motoru
import datetime
import pandas as pd
from PIL import Image
import io
import hashlib
from contextlib import contextmanager

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

# --- 2. KOPMAZ VE GÜVENLİ BULUT VERİTABANI BAĞLANTISI ---
@contextmanager
def vt_baglan():
    """Streamlit Secrets içindeki DATABASE_URL ile internetteki veritabanına bağlanır ve işi bitince kapatır."""
    try:
        baglanti_linki = st.secrets["DATABASE_URL"]
        baglanti = psycopg2.connect(baglanti_linki)
        yield baglanti
    finally:
        if 'baglanti' in locals():
            baglanti.close()

# --- 3. KRİPTOGRAFİK ŞİFRELEME ---
def sifre_hashle(sifre):
    return hashlib.sha256(sifre.encode('utf-8')).hexdigest()

# --- 4. BULUT VERİTABANI VE ŞEMA KURULUMU (POSTGRESQL UYUMLU) ---
def veritabani_hazirla():
    with vt_baglan() as baglanti:
        imlec = baglanti.cursor()
        
        # Sistem Ayarları Tablosu
        imlec.execute("CREATE TABLE IF NOT EXISTS sistem_ayarlari (anahtar TEXT PRIMARY KEY, deger TEXT);")
        
        varsayilan_super_hash = sifre_hashle("esra123")
        imlec.execute("INSERT INTO sistem_ayarlari (anahtar, deger) VALUES ('super_sifre', %s) ON CONFLICT (anahtar) DO NOTHING;", (varsayilan_super_hash,))

        # AVM Listesi Tablosu
        imlec.execute("""
        CREATE TABLE IF NOT EXISTS avm_listesi (
            id SERIAL PRIMARY KEY,
            avm_adi TEXT UNIQUE,
            lisans_bitis TEXT,
            odeme_durumu TEXT DEFAULT 'DENEME SÜRESİ',
            yonetici_sifre TEXT NOT NULL,
            uyari_saati TEXT DEFAULT '22:00'
        );""")

        # Tabloya sonradan eklenebilecek uyari_saati sütunu kontrolü
        imlec.execute("ALTER TABLE avm_listesi ADD COLUMN IF NOT EXISTS uyari_saati TEXT DEFAULT '22:00';")

        # Mağazalar Tablosu
        imlec.execute("""
        CREATE TABLE IF NOT EXISTS magazalar (
            id SERIAL PRIMARY KEY, 
            avm_id INTEGER REFERENCES avm_listesi(id) ON DELETE CASCADE,
            adi TEXT, 
            kat INTEGER,
            sifre TEXT NOT NULL
        );""")

        # Günlük Cirolar Tablosu
        imlec.execute("""
        CREATE TABLE IF NOT EXISTS gunluk_cirolar (
            id SERIAL PRIMARY KEY, 
            avm_id INTEGER REFERENCES avm_listesi(id) ON DELETE CASCADE,
            magaza_id INTEGER REFERENCES magazalar(id) ON DELETE CASCADE, 
            tarih TEXT, 
            kdv_dahil REAL, 
            kdv_haric REAL,
            kasa_foto BYTEA
        );""")
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
                imlec = b.cursor()
                imlec.execute("SELECT deger FROM sistem_ayarlari WHERE anahtar = 'super_sifre';")
                guncel_super_sifre = imlec.fetchone()[0]
            if sifre_hashle(super_sifre_input) == guncel_super_sifre:
                st.session_state.update({"giris_yapildi": True, "kullanici_turu": "super"})
                st.rerun()
            else: st.error("❌ Hatalı Şifre!")

    elif tur == "AVM Yönetimi":
        with vt_baglan() as b:
            imlec = b.cursor()
            imlec.execute("SELECT id, avm_adi FROM avm_listesi;")
            tum_avmler = imlec.fetchall()
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
                    st.session_state.update({"giris_yapildi": True, "kullanici_turu": "yonetim", "aktif_avm_id": avm_sozluk[secilen_avm_adi], "aktif_avm_adi": secilen_avm_adi})
                    st.rerun()
                else: st.error("❌ Hatalı Şifre!")
        else: st.warning("Sistemde henüz kayıtlı AVM bulunmuyor.")
                
    elif tur == "Mağaza Girişi":
        with vt_baglan() as b:
            imlec = b.cursor()
            imlec.execute("SELECT id, avm_adi FROM avm_listesi;")
            avm_ler = imlec.fetchall()
        if avm_ler:
            m_avm_sozluk = {a[1]: a[0] for a in avm_ler}
            g_secilen_avm = st.selectbox("Bulunduğunuz AVM:", list(m_avm_sozluk.keys()))
            with vt_baglan() as b:
                imlec = b.cursor()
                imlec.execute("SELECT id, adi FROM magazalar WHERE avm_id = %s;", (m_avm_sozluk[g_secilen_avm],))
                magazalar = imlec.fetchall()
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
            df_avmler = pd.read_sql_query('SELECT id as "AVM ID", avm_adi as "AVM Adı", lisans_bitis as "Lisans Bitiş", odeme_durumu as "Ödeme Durumu" FROM avm_listesi', b)
        st.dataframe(df_avmler, use_container_width=True)
        
        if not df_avmler.empty:
            with st.expander("🗑️ Bir AVM'yi Sistemden Tamamen Kaldır"):
                silinecek_avm_adi = st.selectbox("Sistemden Silinecek AVM:", df_avmler["AVM Adı"].tolist())
                if st.button("🔴 Seçilen AVM'yi ve Tüm Verilerini SİL", type="primary"):
                    with vt_baglan() as b:
                        imlec = b.cursor()
                        imlec.execute("DELETE FROM avm_listesi WHERE avm_adi = %s;", (silinecek_avm_adi,))
                        b.commit()
                    st.success(f"'{silinecek_avm_adi}' ve tüm alt verileri buluttan güvenle silindi.")
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
                        b.commit()
                    st.success(f"🎉 '{yeni_avm_adi}' başarıyla bulutta oluşturuldu!")
                    st.rerun()
                except Exception: st.error("Bu AVM adı zaten mevcut!")

    # --------------------------------------------------------------------------
    # ROLE 2: AVM YÖNETİCİ PANELİ (GELİŞMİŞ DASHBOARD ENTEGRASYONU)
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
            st.error(f"🚨 **ERİŞİM ENGELLENDİ:** Lisans süreniz dolmuştur! Sistem Sağlayıcınız (Esra) ile görüşün.")
            st.stop()

        secenek = st.sidebar.radio("Yönetim Menüsü:", ["📊 Raporlar & Grafikler", "📸 Kasa Fotoğrafları", "⚙️ Mağaza ve Şifre Ayarları"])
        
        if secenek == "📊 Raporlar & Grafikler":
            st.header(f"📊 {a_adi} Yönetim Kontrol & Analiz Paneli")
            
            # --- 1. KISIM: BUGÜNÜN ANLIK DURUMU ---
            with vt_baglan() as b:
                imlec = b.cursor()
                imlec.execute("SELECT id, adi, kat FROM magazalar WHERE avm_id = %s;", (a_id,))
                t_magazalar = imlec.fetchall()
                imlec.execute("SELECT magaza_id FROM gunluk_cirolar WHERE avm_id = %s AND tarih = %s;", (a_id, tarih_bugun))
                g_magaza_ids = [r[0] for r in imlec.fetchall()]
            
            if t_magazalar:
                gonderen_listesi = [m[1] for m in t_magazalar if m[0] in g_magaza_ids]
                gondermeyen_listesi = [m[1] for m in t_magazalar if m[0] not in g_magaza_ids]
                
                m_col1, m_col2, m_col3 = st.columns(3)
                with m_col1: st.metric("Toplam Mağaza Sayısı", len(t_magazalar))
                with m_col2: st.metric("Bugün Ciro Girenler", len(gonderen_listesi), delta=f"+{len(gonderen_listesi)}", delta_color="inverse" if len(gonderen_listesi)==0 else "normal")
                with m_col3: st.metric("Rapor Beklenenler", len(gondermeyen_listesi), delta=f"-{len(gondermeyen_listesi)}" if len(gondermeyen_listesi)>0 else "0", delta_color="inverse")
                
                with st.expander("🗓️ Bugünün Anlık Rapor Teslim Listesi (Genişlet/Daralt)"):
                    c_gond, c_bek = st.columns(2)
                    with c_gond:
                        st.success(f"✅ Cirosunu Gönderenler ({len(gonderen_listesi)})")
                        if gonderen_listesi: st.write(", ".join([f"**{m}**" for m in gonderen_listesi]))
                        else: st.info("Henüz ciro girişi yapan mağaza yok.")
                    with c_bek:
                        st.error(f"⏳ Ciro Girişi Yapmayanlar ({len(gondermeyen_listesi)})")
                        if gondermeyen_listesi: st.write(", ".join([f"**{m}**" for m in gondermeyen_listesi]))
                        else: st.success("Harika! Tüm mağazalar raporunu teslim etti. 🎉")
            
                # --- 2. KISIM: GEÇMİŞE DÖNÜK GELİŞMİŞ ANALİZ FİLTRELERİ ---
                st.markdown("---")
                st.subheader("🔍 Tarih Aralıklı Gelişmiş Analiz Filtreleri")
                
                f_col1, f_col2, f_col3 = st.columns(3)
                with f_col1:
                    bugun_dt = datetime.date.today()
                    ay_basi_dt = bugun_dt.replace(day=1)
                    tarih_araligi = st.date_input("Analiz Tarih Aralığı Seçin:", [ay_basi_dt, bugun_dt])
                
                magaza_df_all = pd.DataFrame(t_magazalar, columns=["id", "adi", "kat"])
                with f_col2:
                    secilen_magazalar = st.multiselect("Mağaza Filtresi:", ["Tüm Mağazalar"] + magaza_df_all["adi"].tolist(), default="Tüm Mağazalar")
                with f_col3:
                    kat_secenekleri = ["Tüm Katlar"] + sorted(list(magaza_df_all["kat"].unique()))
                    secilen_kat = st.selectbox("Kat Filtresi:", kat_secenekleri)

                # Tarih aralığı geçerlilik kontrolü
                if isinstance(tarih_araligi, list) and len(tarih_araligi) == 2:
                    bas_tar, bit_tar = tarih_araligi
                else:
                    bas_tar = bit_tar = tarih_araligi[0] if isinstance(tarih_araligi, list) else datetime.date.today()

                # Bulut veritabanından filtrelenen verileri çekme (PostgreSQL Tarih Dönüşümü ile)
                with vt_baglan() as b:
                    query = """
                        SELECT 
                            c.tarih, 
                            m.adi as magaza_adi, 
                            m.kat, 
                            c.kdv_dahil, 
                            c.kdv_haric 
                        FROM gunluk_cirolar c 
                        JOIN magazalar m ON c.magaza_id = m.id 
                        WHERE c.avm_id = %s 
                        AND TO_DATE(c.tarih, 'DD-MM-YYYY') BETWEEN %s AND %s
                    """
                    df_analiz = pd.read_sql_query(query, b, params=(a_id, bas_tar, bit_tar))

                if not df_analiz.empty:
                    # Pandas filtreleme adımları
                    if "Tüm Mağazalar" not in secilen_magazalar and secilen_magazalar:
                        df_analiz = df_analiz[df_analiz["magaza_adi"].isin(secilen_magazalar)]
                    if secilen_kat != "Tüm Katlar":
                        df_analiz = df_analiz[df_analiz["kat"] == int(secilen_kat)]

                    if not df_analiz.empty:
                        # Tarihleri doğru sıralamak için geçici datetime sütunu oluşturma
                        df_analiz["tarih_dt"] = pd.to_datetime(df_analiz["tarih"], format="%d-%m-%Y")
                        df_analiz = df_analiz.sort_values("tarih_dt")

                        # --- ÖZET METRİK KARTLARI ---
                        st.markdown("### 📈 Seçili Dönem Performans Özeti")
                        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                        
                        toplam_kdv_dahil = df_analiz["kdv_dahil"].sum()
                        toplam_kdv_haric = df_analiz["kdv_haric"].sum()
                        gunluk_ort_ciro = df_analiz.groupby("tarih")["kdv_dahil"].sum().mean()
                        
                        magaza_ciro_seri = df_analiz.groupby("magaza_adi")["kdv_dahil"].sum()
                        en_iyi_magaza = magaza_ciro_seri.idxmax() if not magaza_ciro_seri.empty else "Veri Yok"
                        en_iyi_ciro = magaza_ciro_seri.max() if not magaza_ciro_seri.empty else 0.0

                        with kpi1: st.metric("Toplam Ciro (KDV Dahil)", f"{toplam_kdv_dahil:,.2f} TL")
                        with kpi2: st.metric("Toplam Ciro (KDV Hariç)", f"{toplam_kdv_haric:,.2f} TL")
                        with kpi3: st.metric("Günlük Ort. Toplam Ciro", f"{gunluk_ort_ciro:,.2f} TL")
                        with kpi4: st.metric("Dönem Ciro Lideri", f"{en_iyi_magaza}", f"{en_iyi_ciro:,.2f} TL")

                        # --- GRAFİKLER VE DETAYLAR SEKME YAPISI ---
                        st.markdown("---")
                        tab_trend, tab_kiyas, tab_tablo = st.tabs(["📈 Ciro Trend Çizgisi", "🏪 Mağaza Dağılım Kıyaslaması", "📋 Detaylı Veri Tablosu & Excel"])
                        
                        with tab_trend:
                            st.subheader("🗓️ Günlük Ciro Değişim Grafiği (Zaman Serisi)")
                            df_trend_pivot = df_analiz.pivot_table(index="tarih_dt", columns="magaza_adi", values="kdv_dahil", aggfunc="sum").fillna(0)
                            st.line_chart(df_trend_pivot)
                            
                        with tab_kiyas:
                            st.subheader("📊 Mağazaların Toplam Dönemsel Ciro Payları")
                            df_magaza_toplam = df_analiz.groupby("magaza_adi")["kdv_dahil"].sum().reset_index()
                            st.bar_chart(data=df_magaza_toplam, x="magaza_adi", y="kdv_dahil")
                            
                        with tab_tablo:
                            st.subheader("📄 Filtrelenmiş Ciro Satır Listesi")
                            gosterilecek_df = df_analiz[["tarih", "magaza_adi", "kat", "kdv_dahil", "kdv_haric"]].copy()
                            st.dataframe(gosterilecek_df, use_container_width=True)
                            
                            # EXCEL BİLGİSAYARA İNDİRME SİHİRBAZI
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                gosterilecek_df.to_excel(writer, index=False, sheet_name='Ciro_Analiz_Raporu')
                            excel_data = output.getvalue()
                            
                            st.download_button(
                                label="📥 Filtrelenmiş Bu Raporu Excel Olarak İndir",
                                data=excel_data,
                                file_name=f"{a_adi}_ciro_raporu_{bas_tar.strftime('%d_%m_%Y')}_{bit_tar.strftime('%d_%m_%Y')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    else: st.info("Seçtiğiniz mağaza veya kat kriterlerine uygun ciro verisi bulunamadı.")
                else: st.info("Seçilen tarih aralığında bulut veritabanında kayıtlı hiçbir ciro verisi bulunmuyor.")
            else: st.warning("Sistemde henüz kayıtlı mağazanız yok. Önce mağaza ayarlarından listenizi yükleyin.")

        elif secenek == "📸 Kasa Fotoğrafları":
            st.header("📸 Z-Raporu Denetimi")
            with vt_baglan() as b:
                imlec = b.cursor()
                imlec.execute("SELECT c.tarih, m.adi, c.kdv_dahil, c.kasa_foto FROM gunluk_cirolar c JOIN magazalar m ON c.magaza_id = m.id WHERE c.avm_id = %s ORDER BY c.id DESC;", (a_id,))
                veriler = imlec.fetchall()
            if veriler:
                for tarih, adi, ciro, foto_blob in veriler:
                    with st.expander(f"📷 {tarih} - {adi} ({ciro} TL)"):
                        if foto_blob: st.image(Image.open(io.BytesIO(bytes(foto_blob))), width=400)
            else: st.info("Fotoğraf bulunamadı.")

        elif secenek == "⚙️ Mağaza ve Şifre Ayarları":
            st.header("⚙️ Mağaza Yönetim Alanı")
            
            # AVM KAPANIŞ / UYARI SAATİ AYARI
            with st.expander("⏰ Ciro Bildirim Zamanlaması"):
                with vt_baglan() as b:
                    imlec = b.cursor()
                    imlec.execute("SELECT uyari_saati FROM avm_listesi WHERE id = %s;", (a_id,))
                    mevcut_saat = imlec.fetchone()[0]
                
                saat_secenekleri = ["18:00", "19:00", "20:00", "21:00", "21:30", "22:00", "22:30", "23:00", "23:30"]
                if mevcut_saat not in saat_secenekleri: saat_secenekleri.append(mevcut_saat)
                saat_secenekleri.sort()
                
                yeni_saat = st.selectbox("Akşam Kapanış Bildirimi Saat Kaçta Başlasın?", saat_secenekleri, index=saat_secenekleri.index(mevcut_saat))
                if st.button("Zamanlamayı Kaydet"):
                    with vt_baglan() as b:
                        imlec = b.cursor()
                        imlec.execute("UPDATE avm_listesi SET uyari_saati = %s WHERE id = %s;", (yeni_saat, a_id))
                        b.commit()
                    st.success(f"⏰ Akşam ciro bildirim saati başarıyla '{yeni_saat}' olarak güncellendi!")
                    st.rerun()

            st.markdown("---")
            # EXCEL ILE TOPLU MAĞAZA YÜKLEME SİHİRBAZI
            with st.expander("📥 Excel Dosyasından Toplu Mağaza Yükle"):
                st.markdown("""
                **🚨 Önemli Kurallar:**
                1. Yükleyeceğiniz Excel dosyasında şu 3 sütun ismi tam olarak yer almalıdır: `Mağaza Adı`, `Kat`, `Giriş Şifresi`
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
                                            imlec.execute("INSERT INTO magazalar (avm_id, adi, kat, sifre) VALUES (%s, %s, %s, %s);", 
                                                           (a_id, m_adi_ex, m_kat_ex, sifre_hashle(m_sifre_ex)))
                                            basarili_kayit += 1
                                    b.commit()
                                st.success(f"🎉 Harika! {basarili_kayit} adet mağaza başarıyla buluta aktarıldı.")
                                st.rerun()
                        else: st.error("🚨 Sütun isimleri uyuşmuyor!")
                    except Exception as e: st.error(f"Excel hatası: {e}")

            st.markdown("---")
            with st.expander("➕ Tek Tek Yeni Mağaza Ekle"):
                yeni_m_adi = st.text_input("Mağaza Adı:")
                yeni_m_kat = st.number_input("Kat:", min_value=-2, max_value=5, value=0)
                yeni_m_sifre = st.text_input("Mağaza Şifresi:", value="1234")
                if st.button("Mağazayı Kaydet"):
                    if yeni_m_adi.strip() != "":
                        with vt_baglan() as b:
                            imlec = b.cursor()
                            imlec.execute("INSERT INTO magazalar (avm_id, adi, kat, sifre) VALUES (%s, %s, %s, %s);", (a_id, yeni_m_adi, yeni_m_kat, sifre_hashle(yeni_m_sifre)))
                            b.commit()
                        st.success(f"✓ {yeni_m_adi} eklendi.")
                        st.rerun()
            
            st.markdown("---")
            with st.expander("🗑️ Mağaza Sil / Sistemden Çıkar"):
                with vt_baglan() as b:
                    imlec = b.cursor()
                    imlec.execute("SELECT id, adi FROM magazalar WHERE avm_id = %s;", (a_id,))
                    mevcut_magazalar = imlec.fetchall()
                if mevcut_magazalar:
                    m_sil_sozluk = {m[1]: m[0] for m in mevcut_magazalar}
                    silinecek_m_adi = st.selectbox("Sistemden Çıkarılacak Mağaza:", list(m_sil_sozluk.keys()))
                    if st.button("🔴 Mağazayı ve Geçmiş Cirolarını Sil", type="primary"):
                        with vt_baglan() as b:
                            imlec = b.cursor()
                            imlec.execute("DELETE FROM magazalar WHERE id = %s;", (m_sil_sozluk[silinecek_m_adi],))
                            b.commit()
                        st.success(f"'{silinecek_m_adi}' mağazası tüm ciro geçmişiyle birlikte silindi.")
                        st.rerun()
                else: st.info("Henüz kayıtlı mağaza yok.")

    # --------------------------------------------------------------------------
    # ROLE 3: MAĞAZA PANELİ (BULUT TABANLI VE ZAMAN KONTROLLÜ)
    # --------------------------------------------------------------------------
    elif st.session_state["kullanici_turu"] == "magaza":
        a_id = st.session_state["aktif_avm_id"]
        m_id = st.session_state["aktif_magaza_id"]
        m_adi = st.session_state["aktif_magaza_adi"]
        
        simdi = datetime.datetime.now()
        su_anki_saat = simdi.strftime("%H:%M")
        tarih_bugun_str = simdi.strftime("%d-%m-%Y")
        tarih_dün_str = (simdi - datetime.timedelta(days=1)).strftime("%d-%m-%Y")
        
        with vt_baglan() as b:
            imlec = b.cursor()
            imlec.execute("SELECT uyari_saati FROM avm_listesi WHERE id = %s;", (a_id,))
            ayar_uyari_saati = imlec.fetchone()[0]
            
            imlec.execute("SELECT COUNT(*) FROM gunluk_cirolar WHERE magaza_id = %s AND tarih = %s;", (m_id, tarih_bugun_str))
            bugun_grid_sayisi = imlec.fetchone()[0]
            
            imlec.execute("SELECT COUNT(*) FROM gunluk_cirolar WHERE magaza_id = %s AND tarih = %s;", (m_id, tarih_dün_str))
            dun_giris_sayisi = imlec.fetchone()[0]
        
        tetiklenen_uyari = None
        if su_anki_saat >= ayar_uyari_saati and bugun_grid_sayisi == 0:
            tetiklenen_uyari = f"🚨 **AKŞAM KAPANIŞ UYARISI:** Bugünün ({tarih_bugun_str}) günlük ciro ve Z-Raporu girişi henüz yapılmamıştır."
        elif su_anki_saat < "14:00" and dun_giris_sayisi == 0:
            tetiklenen_uyari = f"⚠️ **SABAH AÇILIŞ UYARISI:** Dünkü ({tarih_dün_str}) ciro raporunu göndermeyi unuttuğunuz tespit edilmiştir!"
            
        if tetiklenen_uyari:
            st.error(tetiklenen_uyari)
            st.toast(tetiklenen_uyari[:60] + "...", icon="⏰")
            
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
                st.success(f"🎉 {tarih_formatli} tarihi için ciro girişiniz bulutta kayıtlıdır.")
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
                            b.commit()
                        st.success(f"🎉 {tarih_formatli} verileri başarıyla buluta işlendi!")
                        st.rerun()
                    else: st.error("Lütfen z-raporu fotoğrafını sisteme yükleyin!")
                        
        with sekme_rapor:
            with vt_baglan() as b:
                df_magaza_ozel = pd.read_sql_query("SELECT tarih, kdv_dahil, kdv_haric FROM gunluk_cirolar WHERE magaza_id = %s ORDER BY id DESC", b, params=(m_id,))
            if not df_magaza_ozel.empty: st.dataframe(df_magaza_ozel, use_container_width=True)
