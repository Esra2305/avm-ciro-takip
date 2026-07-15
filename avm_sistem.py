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

# --- 1. VERİTABANI BAĞLANTISI ---
@st.cache_resource
def veritabani_havuzu_olustur():
    return ThreadedConnectionPool(1, 10, st.secrets["DATABASE_URL"])

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

# --- 2. YARDIMCI FONKSİYONLAR ---
def sifre_hashle(sifre):
    return hashlib.sha256(sifre.encode('utf-8')).hexdigest()

def sifre_guncelle(kullanici_id, eski_sifre_input, yeni_sifre, tablo):
    with vt_baglan() as b:
        imlec = b.cursor()
        imlec.execute(f"SELECT sifre FROM {tablo} WHERE id = %s;", (kullanici_id,))
        mevcut_hash = imlec.fetchone()[0]
        if sifre_hashle(eski_sifre_input) == mevcut_hash:
            imlec.execute(f"UPDATE {tablo} SET sifre = %s WHERE id = %s;", (sifre_hashle(yeni_sifre), kullanici_id))
            return True, "Şifreniz başarıyla güncellendi!"
        return False, "Eski şifreniz hatalı!"

def resmi_haturlatma_mail_at(magaza_adi, alici_email, tarih):
    if "EMAIL_ADRESI" not in st.secrets or "EMAIL_SIFRESI" not in st.secrets:
        return False, "Sistem ayarlarında mail bilgileri eksik!"
    try:
        msg = MIMEMultipart()
        msg['From'] = st.secrets["EMAIL_ADRESI"]
        msg['To'] = alici_email
        msg['Subject'] = f"⚠️ RESMİ UYARI: Ciro Girişi Gecikmesi - {tarih}"
        msg.attach(MIMEText(f"Sayın {magaza_adi}, {tarih} tarihli ciro veriniz henüz girilmemiştir.", 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(st.secrets["EMAIL_ADRESI"], st.secrets["EMAIL_SIFRESI"])
        server.sendmail(st.secrets["EMAIL_ADRESI"], alici_email, msg.as_string())
        server.quit()
        return True, "Başarılı"
    except Exception as e:
        return False, str(e)

# --- 3. ŞEMA KURULUMU ---
def veritabani_hazirla():
    with vt_baglan() as b:
        imlec = b.cursor()
        imlec.execute("CREATE TABLE IF NOT EXISTS sistem_ayarlari (anahtar TEXT PRIMARY KEY, deger TEXT);")
        imlec.execute("INSERT INTO sistem_ayarlari (anahtar, deger) VALUES ('super_sifre', %s) ON CONFLICT (anahtar) DO NOTHING;", (sifre_hashle("esra123"),))
        imlec.execute("CREATE TABLE IF NOT EXISTS avm_listesi (id SERIAL PRIMARY KEY, avm_adi TEXT UNIQUE, lisans_bitis TEXT, yonetici_sifre TEXT NOT NULL);")
        imlec.execute("CREATE TABLE IF NOT EXISTS magazalar (id SERIAL PRIMARY KEY, avm_id INTEGER REFERENCES avm_listesi(id) ON DELETE CASCADE, adi TEXT, kat INTEGER, sifre TEXT NOT NULL, eposta TEXT);")
        imlec.execute("CREATE TABLE IF NOT EXISTS gunluk_cirolar (id SERIAL PRIMARY KEY, avm_id INTEGER REFERENCES avm_listesi(id) ON DELETE CASCADE, magaza_id INTEGER REFERENCES magazalar(id) ON DELETE CASCADE, tarih TEXT, kdv_dahil REAL, kdv_haric REAL, kasa_foto BYTEA);")
        imlec.execute("CREATE TABLE IF NOT EXISTS aktif_oturumlar (token TEXT PRIMARY KEY, kullanici_turu TEXT, avm_id INTEGER, avm_adi TEXT, magaza_id INTEGER, magaza_adi TEXT);")

veritabani_hazirla()
tarih_bugun = datetime.date.today().strftime("%d-%m-%Y")

# --- 4. OTURUM YÖNETİMİ ---
if "giris_yapildi" not in st.session_state:
    st.session_state.update({"giris_yapildi": False, "kullanici_turu": None})

def oturum_baslat(tur, a_id=None, a_adi=None, m_id=None, m_adi=None):
    token = str(uuid.uuid4())
    with vt_baglan() as b:
        b.cursor().execute("INSERT INTO aktif_oturumlar (token, kullanici_turu, avm_id, avm_adi, magaza_id, magaza_adi) VALUES (%s, %s, %s, %s, %s, %s);", (token, tur, a_id, a_adi, m_id, m_adi))
    st.query_params["token"] = token
    st.session_state.update({"giris_yapildi": True, "kullanici_turu": tur, "aktif_avm_id": a_id, "aktif_avm_adi": a_adi, "aktif_magaza_id": m_id, "aktif_magaza_adi": m_adi})
    st.rerun()

# --- 5. ARAYÜZ ---
if not st.session_state["giris_yapildi"]:
    st.header("🔐 AVM Ciro Giriş Paneli")
    tur = st.selectbox("Giriş Türü:", ["Mağaza Girişi", "AVM Yönetimi"])
    # (Buraya giriş mantığını aynı şekilde koruyabilirsin)
    # --- Giriş işlemleri kodun burada ---
else:
    # --- YÖNETİM VE MAĞAZA İÇİN ŞİFRE GÜNCELLEME ALANI ---
    with st.sidebar.expander("🔑 Şifremi Değiştir"):
        eski = st.text_input("Eski Şifre", type="password")
        yeni = st.text_input("Yeni Şifre", type="password")
        if st.button("Şifreyi Güncelle"):
            tablo = "avm_listesi" if st.session_state["kullanici_turu"] == "yonetim" else "magazalar"
            k_id = st.session_state["aktif_avm_id"] if st.session_state["kullanici_turu"] == "yonetim" else st.session_state["aktif_magaza_id"]
            basari, mesaj = sifre_guncelle(k_id, eski, yeni, tablo)
            if basari: st.success(mesaj)
            else: st.error(mesaj)

    # --- Uygulamanın geri kalan panelleri (Raporlar, Giriş vb.) buraya gelecek ---
    st.write(f"Hoş geldin, {st.session_state.get('aktif_magaza_adi') or st.session_state.get('aktif_avm_adi')}")
