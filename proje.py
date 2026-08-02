"""
Fed Speak — Merkez Bankası Şahin/Güvercin Tonlama Analizi
===========================================================
Fed'in tek bir kelimesi piyasayı uçurur ya da yere çakar. Bu script:

1) federalreserve.gov'un resmi FOMC takvim sayfasından son ~10 FOMC toplantısının
   basın açıklaması (statement) linklerini GERÇEKTEN scrape eder,
2) Her açıklamanın tam metnini çeker ve temizler,
3) Metni finans-duyarlı bir şahin (hawkish/sıkılaştırma) - güvercin (dovish/gevşeme)
   KELİME SÖZLÜĞÜ ile tarar; basit negasyon tespiti ("not tightening" gibi) uygular,
4) yfinance'ten gerçek piyasa verisiyle (10Y getiri, 5Y getiri proxy, DXY, S&P 500)
   her açıklama tarihi etrafında ±3 işlem günlük olay penceresi tepkisi ölçer,
5) Tonlama skorunun piyasa tepkisiyle gerçekten ilişkili olup olmadığını (küçük
   örneklemle, dürüstçe) test eder.

DÜRÜSTLÜK NOTU (kod başında, README'de de tekrarlanıyor):
Bu bir finBERT/dil-modeli SINIFLANDIRMASI DEĞİLDİR. Kelime frekansı tabanlı, basit
ve açıklanabilir bir yöntemdir — bağlamı, ironiyi, cümle yapısını tam kavrayamaz.
Negasyon için sınırlı bir düzeltme uygulanmıştır (cümle içi son 6 kelimede
not/no/without/never taraması) ama bu da mükemmel değildir. Sınırlamalar README'de
açıkça yazılıyor.

Yazar: Claude (Fable beyni ile) — Hakan için quant showcase projesi, 2026-08-02
"""

from __future__ import annotations

import re
import time
import warnings
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
from plotly.subplots import make_subplots
from wordcloud import WordCloud

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# 0. YOL, SABİTLER, RENK PALETİ
# ---------------------------------------------------------------------------

PROJE_KOK = Path(__file__).resolve().parent
GORSEL_DIZIN = PROJE_KOK / "gorseller"
VERI_DIZIN = PROJE_KOK / "veri"
METIN_DIZIN = VERI_DIZIN / "fomc_metinleri"
for d in (GORSEL_DIZIN, VERI_DIZIN, METIN_DIZIN):
    d.mkdir(exist_ok=True)

BUGUN = pd.Timestamp(datetime.now().date())
SON_KAC_TOPLANTI = 10
PENCERE_GUN = 3  # olay penceresi: ±3 işlem günü

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) fed-speak-showcase-research/1.0 "
        "(personal/educational quant analysis project, contact: hakan)"
    )
}

# Diverging renk çifti (kırmızı=şahin/sıkılaştırma, mavi=güvercin/gevşeme,
# gri=nötr) — dataviz kılavuzunun doğrulanmış blue<->red diverging çiftinden.
SAHIN_RENK = "#e34948"
GUVERCIN_RENK = "#2a78d6"
NOTR_GRI = "#8a8a86"
NOTR_BANT = "rgba(138,138,134,0.12)"

ORTAK_TEMA = dict(
    template="plotly_white",
    font=dict(family="Arial, sans-serif", size=13),
    margin=dict(l=70, r=40, t=95, b=60),
)

VARLIK_ADI = {
    "^TNX": "10 Yıllık Hazine Getirisi",
    "^FVX": "5 Yıllık Hazine Getirisi (kısa/orta vade proxy)",
    "DX-Y.NYB": "Dolar Endeksi (DXY)",
    "^GSPC": "S&P 500",
}
GETIRI_TICKERLARI = {"^TNX", "^FVX"}  # bu ikisi zaten yüzde cinsinden kote -> fark = baz puan

print("=" * 72)
print("FED SPEAK — Şahin/Güvercin Tonlama Analizi — başlıyor")
print(f"Referans tarih (bugün): {BUGUN.date()}")
print("=" * 72)

# ---------------------------------------------------------------------------
# 1. FOMC TAKVİMİ — federalreserve.gov'dan gerçek toplantı/statement linkleri
# ---------------------------------------------------------------------------

print("\n[1/7] federalreserve.gov FOMC takvim sayfası çekiliyor...")


def fomc_toplanti_linkleri_cek() -> pd.DataFrame:
    """federalreserve.gov/monetarypolicy/fomccalendars.htm sayfasını çeker,
    her toplantı satırını parse eder. 'notation vote' (ör. Ağustos 2025'teki
    Statement on Longer-Run Goals oylaması gibi düzenli faiz kararı OLMAYAN)
    satırları bilinçli olarak dışlanır — bunlar bir para politikası açıklaması
    değil, farklı bir belge türüdür."""
    url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    rows = soup.find_all("div", class_=lambda c: c and "fomc-meeting" in c and "row" in c)

    kayitlar = []
    for row in rows:
        metin = row.get_text(" ", strip=True)
        linkler = [
            a["href"] for a in row.find_all("a", href=True)
            if re.fullmatch(r"/newsevents/pressreleases/monetary\d{8}a\.htm", a["href"])
        ]
        if not linkler:
            continue
        if "notation vote" in metin.lower():
            print(f"  atlandı (düzenli faiz kararı değil, notation vote): {metin[:65]}...")
            continue
        tarih_str = re.search(r"monetary(\d{8})a\.htm", linkler[0]).group(1)
        kayitlar.append(dict(
            tarih=pd.Timestamp(datetime.strptime(tarih_str, "%Y%m%d")),
            url="https://www.federalreserve.gov" + linkler[0],
        ))
    df = pd.DataFrame(kayitlar).drop_duplicates("tarih").sort_values("tarih").reset_index(drop=True)
    return df


takvim_df = fomc_toplanti_linkleri_cek()
gecmis_df = takvim_df[takvim_df["tarih"] <= BUGUN].tail(SON_KAC_TOPLANTI).reset_index(drop=True)
print(f"  Takvimde toplam {len(takvim_df)} düzenli FOMC faiz kararı toplantısı bulundu "
      f"(2021'den bugüne, resmi sayfanın kapsadığı aralık).")
print(f"  Bugüne kadar geçmiş olan son {len(gecmis_df)} toplantı analiz için seçildi: "
      f"{gecmis_df['tarih'].min().date()} -> {gecmis_df['tarih'].max().date()}")
takvim_df.to_csv(VERI_DIZIN / "fomc_takvimi_tum_toplantilar.csv", index=False)

# ---------------------------------------------------------------------------
# 2. HER TOPLANTI İÇİN STATEMENT METNİ — gerçekten çekiliyor, uydurulmuyor
# ---------------------------------------------------------------------------

print(f"\n[2/7] {len(gecmis_df)} FOMC açıklamasının tam metni çekiliyor "
      f"(isteklerin arasında 1.5 sn bekleme, siteye saygılı davranmak için)...")


def statement_metni_cek(url: str, max_deneme: int = 3) -> str | None:
    for deneme in range(1, max_deneme + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
        except requests.RequestException as e:
            print(f"    ağ hatası ({deneme}/{max_deneme}): {e}")
            time.sleep(2 * deneme)
            continue
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            article = soup.find("div", id="article")
            if article is None:
                return None
            return article.get_text("\n", strip=True)
        print(f"    HTTP {r.status_code} ({deneme}/{max_deneme}), tekrar deneniyor...")
        time.sleep(2 * deneme)
    return None


def metin_temizle(ham_metin: str) -> str:
    """federalreserve.gov statement sayfalarının sabit HTML boilerplate'ini
    ('For release at...', 'Share', iletişim/e-posta bilgisi, 'Implementation
    Note issued...') gövdeden ayıklar. 'Share' işaretinden 'For media
    inquiries'e kadar olan kısım gerçek Committee metnidir."""
    satirlar = [s.strip() for s in ham_metin.split("\n") if s.strip()]
    baslangic = 0
    for i, s in enumerate(satirlar):
        if s.lower() == "share":
            baslangic = i + 1
            break
    bitis = len(satirlar)
    for i, s in enumerate(satirlar):
        if s.lower().startswith("for media inquiries"):
            bitis = i
            break
    return " ".join(satirlar[baslangic:bitis])


metinler = {}
basarisiz = []
for i, row in gecmis_df.iterrows():
    tarih_str = row["tarih"].strftime("%Y-%m-%d")
    print(f"  [{i+1}/{len(gecmis_df)}] {tarih_str} -> {row['url']}")
    ham = statement_metni_cek(row["url"])
    if ham is None:
        print(f"    ÇEKİLEMEDİ, bu toplantı analizden dışlanıyor (uydurma metin üretilmiyor).")
        basarisiz.append(tarih_str)
        time.sleep(1.5)
        continue
    temiz = metin_temizle(ham)
    metinler[tarih_str] = temiz
    (METIN_DIZIN / f"{tarih_str}_fomc_statement.txt").write_text(temiz, encoding="utf-8")
    print(f"    OK — {len(temiz.split())} kelime")
    time.sleep(1.5)

print(f"\n  Sonuç: {len(metinler)}/{len(gecmis_df)} açıklama gerçekten çekildi ve kullanılabilir.")
if basarisiz:
    print(f"  Çekilemeyenler (dışlandı): {basarisiz}")

gecmis_df = gecmis_df[gecmis_df["tarih"].dt.strftime("%Y-%m-%d").isin(metinler.keys())].reset_index(drop=True)

# ---------------------------------------------------------------------------
# 3. ŞAHİN / GÜVERCİN KELİME SÖZLÜĞÜ + NEGASYON DÜZELTMESİ
# ---------------------------------------------------------------------------
print("\n[3/7] Şahin/güvercin kelime sözlüğü ile tonlama skorlanıyor...")

# Kaynak: görev talimatındaki örnek kelimeler (tighten/restrictive/elevated
# inflation/further increases/vigilant <-> accommodative/patient/gradual/
# support the economy/downside risks) + Fed-speak literatüründe yerleşik ek
# ifadeler (dissent cümlelerindeki "raise/lower the target range" dahil).
# GÜVEN: MEDIUM — akademik/onaylı bir sözlük değil, alan bilgisiyle
# derlenmiş bir hipotez; README'de sınırlamalarıyla birlikte açıkça yazılıyor.
LEKSIKON_HAM = [
    # (regex_govde, görünen_ifade, kategori)
    (r"quantitative\s+tightening", "quantitative tightening", "sahin"),
    (r"withdraw\w*\s+accommodation", "withdraw accommodation", "sahin"),
    (r"higher\s+for\s+longer", "higher for longer", "sahin"),
    (r"highly\s+attentive", "highly attentive", "sahin"),
    (r"upside\s+risks?\s+to\s+inflation", "upside risk(s) to inflation", "sahin"),
    (r"persistent(?:ly)?\s+(?:high\s+)?inflation", "persistent(ly) (high) inflation", "sahin"),
    (r"further\s+increases?", "further increase(s)", "sahin"),
    (r"raise[sd]?\s+the\s+target\s+range", "raise the target range", "sahin"),
    # NOT: "strongly committed" bilinçli olarak leksikondan ÇIKARILDI — ilk
    # taramada 10 açıklamanın 8'inde "The Committee is strongly committed to
    # supporting maximum employment and returning inflation to its 2 percent
    # objective" cümlesinin BİREBİR AYNI (sabit şablon/boilerplate) olduğu
    # görüldü; tonlama ile hiçbir ilişkisi yok, sadece o paragrafın o
    # açıklamada kullanılıp kullanılmadığını ölçüyordu. README'de bu keşif
    # ayrıca not düşülüyor.
    (r"somewhat\s+elevated", "somewhat elevated", "sahin"),
    (r"above\s+(?:the\s+committee'?s\s+)?2\s*percent", "above 2 percent", "sahin"),
    (r"tighten\w*", "tighten(ing/ed)", "sahin"),
    (r"restrictive", "restrictive", "sahin"),
    (r"hike[sd]?", "hike(s/d)", "sahin"),
    (r"firming", "firming", "sahin"),
    (r"vigilant", "vigilant", "sahin"),
    (r"resolute", "resolute", "sahin"),
    (r"overheat\w*", "overheat(ing)", "sahin"),
    (r"unanchor\w*", "unanchored", "sahin"),
    # --- güvercin ---
    (r"lower[sd]?\s+the\s+target\s+range", "lower the target range", "guvercin"),
    (r"reduce\s+the\s+target\s+range", "reduce the target range", "guvercin"),
    (r"support\w*\s+(?:the\s+)?economic\s+activity", "support economic activity", "guvercin"),
    (r"support\w*\s+the\s+economy", "support the economy", "guvercin"),
    (r"downside\s+risks?", "downside risk(s)", "guvercin"),
    (r"patien\w*", "patient/patience", "guvercin"),
    (r"gradual(?:ly)?", "gradual(ly)", "guvercin"),
    (r"accommodat\w*", "accommodative/accommodation", "guvercin"),
    (r"ample", "ample", "guvercin"),
    (r"eas(?:e[sd]?|ing)(?:\s+policy)?", "ease/easing (policy)", "guvercin"),
    (r"slack", "slack", "guvercin"),
    (r"soften\w*", "soften(ing)", "guvercin"),
    (r"pause[sd]?", "pause(d/s)", "guvercin"),
    (r"moderat(?:e|ed|ing)", "moderate(d/ing)", "guvercin"),
    (r"weaken\w*", "weaken(ing)", "guvercin"),
    (r"cut(?:s|ting)?", "cut(s/ting)", "guvercin"),
]

NEGASYON_KELIMELERI = {"not", "no", "never", "without", "unlikely", "avoid", "nor", "neither"}


def _kelime_uzunlugu(pattern: str) -> int:
    return len(re.findall(r"[a-zA-Z]+", pattern))


# Uzun/spesifik ifadeler önce taranır ki örtüşen kısa kökler (ör. "accommodat*")
# zaten "withdraw accommodation" gibi daha spesifik bir ifadeyle eşleşmiş metni
# tekrar saymasın (aynı karakter aralığı maskelenir).
LEKSIKON = sorted(
    [(re.compile(r"\b(?:" + p + r")\b", re.IGNORECASE), ifade, kategori)
     for p, ifade, kategori in LEKSIKON_HAM],
    key=lambda x: _kelime_uzunlugu(x[0].pattern), reverse=True,
)


def cumlelere_ayir(metin: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<=[.!?])\s+", metin) if c.strip()]


def cumlede_tara(cumle: str) -> list[dict]:
    """Bir cümle içindeki tüm leksikon eşleşmelerini bulur (uzundan kısaya,
    çakışan aralıkları tekrar saymadan) ve her biri için basit negasyon
    kontrolü yapar (eşleşmeden önceki 6 kelimede not/no/without/never vb var mı)."""
    maskeli = [False] * (len(cumle) + 1)
    kelime_araliklari = [(m.start(), m.end()) for m in re.finditer(r"[A-Za-z']+", cumle)]
    bulgular = []
    for regex, ifade, kategori in LEKSIKON:
        for m in regex.finditer(cumle):
            b, e = m.span()
            if any(maskeli[b:e]):
                continue
            for i in range(b, e):
                maskeli[i] = True
            onceki = [cumle[a:c].lower() for (a, c) in kelime_araliklari if c <= b][-6:]
            negatif_mi = any(k in NEGASYON_KELIMELERI or k.endswith("n't") for k in onceki)
            kategori_son = kategori
            if negatif_mi:
                kategori_son = "guvercin" if kategori == "sahin" else "sahin"
            bulgular.append(dict(ifade=ifade, esleyen_metin=m.group(), kategori_ham=kategori,
                                  negatif_mi=negatif_mi, kategori_son=kategori_son))
    return bulgular


tonlama_kayitlari = []
sahin_kelime_sayaci: Counter = Counter()
guvercin_kelime_sayaci: Counter = Counter()
toplam_negasyon_flip = 0

for tarih_str, metin in metinler.items():
    kelime_sayisi = len(re.findall(r"[A-Za-z']+", metin))
    tum_bulgular = []
    for cumle in cumlelere_ayir(metin):
        tum_bulgular.extend(cumlede_tara(cumle))

    sahin_n = sum(1 for b in tum_bulgular if b["kategori_son"] == "sahin")
    guvercin_n = sum(1 for b in tum_bulgular if b["kategori_son"] == "guvercin")
    flip_n = sum(1 for b in tum_bulgular if b["negatif_mi"])
    toplam_negasyon_flip += flip_n

    for b in tum_bulgular:
        hedef = sahin_kelime_sayaci if b["kategori_son"] == "sahin" else guvercin_kelime_sayaci
        hedef[b["esleyen_metin"].lower()] += 1

    skor = (sahin_n - guvercin_n) / kelime_sayisi * 1000  # binde (per-mille) yoğunluk

    tonlama_kayitlari.append(dict(
        tarih=pd.Timestamp(tarih_str), kelime_sayisi=kelime_sayisi,
        sahin_vurgu=sahin_n, guvercin_vurgu=guvercin_n, negasyon_flip=flip_n,
        tonlama_skoru=skor,
    ))
    print(f"  {tarih_str}: {kelime_sayisi} kelime, şahin={sahin_n}, güvercin={guvercin_n}, "
          f"negasyon_flip={flip_n}, tonlama_skoru={skor:+.2f}")

tonlama_df = pd.DataFrame(tonlama_kayitlari).sort_values("tarih").reset_index(drop=True)
tonlama_df.to_csv(VERI_DIZIN / "tonlama_skorlari.csv", index=False)
print(f"\n  Toplam {toplam_negasyon_flip} eşleşme negasyon nedeniyle ters kategoriye çevrildi.")
print(f"  Tonlama skoru aralığı: {tonlama_df['tonlama_skoru'].min():+.2f} .. "
      f"{tonlama_df['tonlama_skoru'].max():+.2f} (binde, pozitif=şahin, negatif=güvercin)")

NOTR_ESIK = max(1.0, tonlama_df["tonlama_skoru"].std() * 0.35)  # görsel nötr bant genişliği

# ---------------------------------------------------------------------------
# 4. PİYASA VERİSİ (yfinance) — 10Y/5Y getiri, DXY, S&P 500
# ---------------------------------------------------------------------------
print(f"\n[4/7] yfinance'ten piyasa verisi indiriliyor "
      f"({', '.join(VARLIK_ADI.values())})...")
import yfinance as yf

baslangic = (gecmis_df["tarih"].min() - timedelta(days=15)).strftime("%Y-%m-%d")
bitis = (BUGUN + timedelta(days=2)).strftime("%Y-%m-%d")

fiyat_cache: dict[str, pd.DataFrame] = {}
for ticker in VARLIK_ADI:
    try:
        df = yf.download(ticker, start=baslangic, end=bitis, interval="1d", progress=False)
        if df.empty:
            print(f"  UYARI: {ticker} boş döndü, atlanıyor.")
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        fiyat_cache[ticker] = df
        print(f"  {ticker} ({VARLIK_ADI[ticker]}): {len(df)} günlük bar, "
              f"{df.index.min().date()} -> {df.index.max().date()}")
    except Exception as e:
        print(f"  HATA: {ticker} indirilemedi ({e}), bu varlık analizden çıkarılıyor.")

# ---------------------------------------------------------------------------
# 5. OLAY PENCERESİ — ±3 işlem günü, açıklama tarihi etrafında
# ---------------------------------------------------------------------------
print(f"\n[5/7] Her açıklama için ±{PENCERE_GUN} işlem günlük olay penceresi tepkisi hesaplanıyor...")


def olay_penceresi(df: pd.DataFrame, tarih: pd.Timestamp, pencere: int = PENCERE_GUN) -> dict | None:
    """Açıklama tarihine en yakın (<=) işlem gününü referans (offset 0) alır,
    -pencere..+pencere işlem günü aralığındaki kapanışları döndürür. Gelecekte
    henüz oluşmamış barlar için None/NaN bırakır (uydurulmaz)."""
    idx = df.index.searchsorted(tarih)
    if idx >= len(df) or df.index[idx] != tarih:
        # tam eşleşme yoksa (tatil/veri boşluğu), bir önceki günü referans al
        idx = df.index.searchsorted(tarih, side="right") - 1
    if idx < pencere:
        return None  # önce yeterli geçmiş yok
    sonuc = {}
    for off in range(-pencere, pencere + 1):
        pos = idx + off
        sonuc[off] = float(df["Close"].iloc[pos]) if 0 <= pos < len(df) else np.nan
    return sonuc


olay_kayitlari = []
for ticker, df in fiyat_cache.items():
    for _, row in gecmis_df.iterrows():
        pencere = olay_penceresi(df, row["tarih"])
        if pencere is None:
            continue
        ref = pencere[-1]  # açıklamadan bir önceki kapanış (baz alınan referans)
        kayit = dict(tarih=row["tarih"], varlik=ticker, varlik_adi=VARLIK_ADI[ticker])
        for off, deger in pencere.items():
            kayit[f"kapanis_t{off:+d}" if off != 0 else "kapanis_t0"] = deger
        if ticker in GETIRI_TICKERLARI:
            kayit["degisim_birimi"] = "baz_puan"
            kayit["tepki_0g"] = (pencere[0] - pencere[-1]) * 100 if not np.isnan(pencere[0]) else np.nan
            kayit["tepki_3g"] = (
                (pencere[3] - pencere[-1]) * 100
                if 3 in pencere and not np.isnan(pencere.get(3, np.nan)) else np.nan
            )
        else:
            kayit["degisim_birimi"] = "yuzde"
            kayit["tepki_0g"] = (pencere[0] - pencere[-1]) / pencere[-1] * 100 if not np.isnan(pencere[0]) else np.nan
            kayit["tepki_3g"] = (
                (pencere[3] - pencere[-1]) / pencere[-1] * 100
                if 3 in pencere and not np.isnan(pencere.get(3, np.nan)) else np.nan
            )
        # Karşılaştırılabilirlik için TÜM varlıklarda ayrıca yüzde-değişim de tutulur
        # (heatmap/scatter'da ortak eksende gösterilebilsin diye; getiri varlıklarında
        # bp daha standart okunur ama % de matematiksel olarak geçerli bir ek görünüm).
        kayit["tepki_0g_yuzde"] = (pencere[0] - pencere[-1]) / pencere[-1] * 100 if not np.isnan(pencere[0]) else np.nan
        olay_kayitlari.append(kayit)

olay_df = pd.DataFrame(olay_kayitlari).merge(
    tonlama_df[["tarih", "tonlama_skoru"]], on="tarih", how="left"
)
olay_df.to_csv(VERI_DIZIN / "olay_penceresi_tepkileri.csv", index=False)

tam_pencere_n = olay_df["tepki_3g"].notna().sum()
print(f"  {len(olay_df)} açıklama x varlık kombinasyonu hesaplandı; "
      f"{tam_pencere_n} tanesinde tam ±{PENCERE_GUN} günlük pencere mevcuttu "
      f"(en yakın toplantılarda +{PENCERE_GUN} gün henüz oluşmamış olabilir, o hücreler NaN).")


def pearson_r(x: np.ndarray, y: np.ndarray) -> float:
    mask = ~(np.isnan(x) | np.isnan(y))
    if mask.sum() < 3:
        return np.nan
    x, y = x[mask], y[mask]
    if x.std() == 0 or y.std() == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


korelasyonlar = {}
for ticker in VARLIK_ADI:
    alt = olay_df[olay_df["varlik"] == ticker]
    if len(alt) < 3:
        continue
    r = pearson_r(alt["tonlama_skoru"].values, alt["tepki_0g"].values)
    korelasyonlar[ticker] = r
    print(f"  {VARLIK_ADI[ticker]}: tonlama skoru <-> açıklama-günü tepkisi, Pearson r = {r:+.3f} (n={len(alt)})")

pd.Series(korelasyonlar, name="pearson_r").to_csv(VERI_DIZIN / "tonlama_piyasa_korelasyonu.csv")

# ---------------------------------------------------------------------------
# 6. GÖRSELLER
# ---------------------------------------------------------------------------
print("\n[6/7] Görseller üretiliyor...")


def kaydet(fig: go.Figure, dosya_adi: str, genislik=1200, yukseklik=700):
    html_yolu = GORSEL_DIZIN / f"{dosya_adi}.html"
    png_yolu = GORSEL_DIZIN / f"{dosya_adi}.png"
    fig.write_html(html_yolu)
    try:
        fig.write_image(png_yolu, width=genislik, height=yukseklik, scale=2)
    except Exception as e:
        print(f"  UYARI: {dosya_adi} PNG'ye çevrilemedi ({e}), sadece HTML kaydedildi.")
    print(f"  kaydedildi -> {html_yolu.name} / {png_yolu.name}")


# --- Görsel 1: Zaman içinde tonlama skoru (nötr bant ile) -------------------
renkler_1 = [
    SAHIN_RENK if s > NOTR_ESIK else (GUVERCIN_RENK if s < -NOTR_ESIK else NOTR_GRI)
    for s in tonlama_df["tonlama_skoru"]
]
fig1 = go.Figure()
fig1.add_hrect(y0=-NOTR_ESIK, y1=NOTR_ESIK, fillcolor=NOTR_BANT, line_width=0,
                annotation_text="nötr bant", annotation_position="top left",
                annotation_font=dict(size=10, color=NOTR_GRI))
fig1.add_hline(y=0, line_color=NOTR_GRI, line_width=1, line_dash="dot")
fig1.add_trace(go.Scatter(
    x=tonlama_df["tarih"], y=tonlama_df["tonlama_skoru"], mode="lines+markers",
    line=dict(color="#52514e", width=2),
    marker=dict(color=renkler_1, size=12, line=dict(color="white", width=1)),
    text=[f"{t.date()}" for t in tonlama_df["tarih"]],
    hovertemplate="%{text}<br>Tonlama skoru: %{y:+.2f}<extra></extra>",
))
fig1.update_layout(
    **ORTAK_TEMA,
    title="Zaman İçinde FOMC Tonlama Skoru<br>"
          "<sup>pozitif = şahin (sıkılaştırma) ağır basıyor · negatif = güvercin (gevşeme) ağır basıyor · "
          "kırmızı/mavi nokta = nötr bandın dışında</sup>",
    xaxis_title="Toplantı tarihi", yaxis_title="Tonlama skoru (binde, şahin - güvercin yoğunluğu)",
    showlegend=False, height=560,
)
kaydet(fig1, "01_zaman_icinde_tonlama_skoru")

# --- Görsel 2: Tonlama vs piyasa tepkisi (varlık başına küçük çoklu) --------
tickerlar_sirali = [t for t in VARLIK_ADI if t in fiyat_cache]
fig2 = make_subplots(
    rows=2, cols=2, subplot_titles=[VARLIK_ADI[t] for t in tickerlar_sirali],
    horizontal_spacing=0.10, vertical_spacing=0.16,
)
for i, ticker in enumerate(tickerlar_sirali):
    r, c = i // 2 + 1, i % 2 + 1
    alt = olay_df[(olay_df["varlik"] == ticker) & olay_df["tepki_0g"].notna()]
    birim = "bp" if ticker in GETIRI_TICKERLARI else "%"
    renkler = [SAHIN_RENK if s > 0 else GUVERCIN_RENK for s in alt["tonlama_skoru"]]
    fig2.add_trace(go.Scatter(
        x=alt["tonlama_skoru"], y=alt["tepki_0g"], mode="markers",
        marker=dict(color=renkler, size=11, line=dict(color="white", width=1)),
        text=[f"{t.date()}" for t in alt["tarih"]],
        hovertemplate=f"%{{text}}<br>Tonlama: %{{x:+.2f}}<br>Tepki: %{{y:+.2f}} {birim}<extra></extra>",
        showlegend=False,
    ), row=r, col=c)
    if len(alt) >= 3 and alt["tonlama_skoru"].std() > 0:
        egim, kesisim = np.polyfit(alt["tonlama_skoru"], alt["tepki_0g"], 1)
        x_cizgi = np.linspace(alt["tonlama_skoru"].min(), alt["tonlama_skoru"].max(), 20)
        fig2.add_trace(go.Scatter(
            x=x_cizgi, y=egim * x_cizgi + kesisim, mode="lines",
            line=dict(color="#52514e", width=1.5, dash="dash"), showlegend=False,
            hoverinfo="skip",
        ), row=r, col=c)
        r_deger = korelasyonlar.get(ticker, np.nan)
        fig2.add_annotation(
            text=f"r = {r_deger:+.2f} (n={len(alt)})", xref=f"x{i+1 if i else ''} domain",
            yref=f"y{i+1 if i else ''} domain", x=0.05, y=0.95, showarrow=False,
            font=dict(size=11, color="#333"), align="left", row=r, col=c,
            bgcolor="rgba(255,255,255,0.85)", borderpad=3,
        )
    fig2.update_yaxes(title_text=f"Açıklama-günü tepkisi ({birim})", row=r, col=c)
    fig2.update_xaxes(title_text="Tonlama skoru", row=r, col=c, zeroline=True, zerolinecolor=NOTR_GRI)
    fig2.add_hline(y=0, line_color=NOTR_GRI, line_width=0.8, row=r, col=c)
fig2.update_layout(
    **ORTAK_TEMA,
    title="Tonlama Skoru vs Açıklama-Günü Piyasa Tepkisi<br>"
          "<sup>şahin dedikçe faiz/dolar gerçekten yukarı mı gidiyor? kırmızı=şahin toplantı, mavi=güvercin toplantı</sup>",
    height=760,
)
kaydet(fig2, "02_tonlama_vs_piyasa_tepkisi_scatter", yukseklik=760)

# --- Görsel 3: Kelime bulutu (leksikonda eşleşen ifadeler) ------------------
tum_frekans = {}
for k, v in sahin_kelime_sayaci.items():
    tum_frekans[f"{k} (şahin)"] = v
for k, v in guvercin_kelime_sayaci.items():
    tum_frekans[f"{k} (güvercin)"] = v

SAHIN_ETIKETLI = {f"{k} (şahin)" for k in sahin_kelime_sayaci}


def renk_fonksiyonu(word, **kwargs):
    return SAHIN_RENK if word in SAHIN_ETIKETLI else GUVERCIN_RENK


if tum_frekans:
    wc = WordCloud(
        width=1600, height=900, background_color="white",
        color_func=renk_fonksiyonu, prefer_horizontal=0.92,
        max_words=60, relative_scaling=0.55, margin=8,
        font_path=None,
    ).generate_from_frequencies(tum_frekans)
    wc_yolu = GORSEL_DIZIN / "03_one_cikan_ifadeler_kelime_bulutu.png"
    wc.to_file(str(wc_yolu))
    print(f"  kaydedildi -> {wc_yolu.name} (kırmızı=şahin ifade, mavi=güvercin ifade)")
else:
    print("  UYARI: leksikon hiç eşleşme bulamadı, kelime bulutu atlandı.")

# --- Görsel 4: Olay penceresi — 10Y getiri ve DXY hareketi ------------------
fig4 = make_subplots(
    rows=1, cols=2,
    subplot_titles=["10 Yıllık Hazine Getirisi (^TNX) — kümülatif baz puan değişimi",
                     "Dolar Endeksi (DXY) — kümülatif % değişim"],
    horizontal_spacing=0.10,
)
sahin_gosterildi, guvercin_gosterildi = False, False
for _, row in gecmis_df.iterrows():
    skor_row = tonlama_df.loc[tonlama_df["tarih"] == row["tarih"], "tonlama_skoru"]
    if skor_row.empty:
        continue
    skor = skor_row.iloc[0]
    renk = SAHIN_RENK if skor > 0 else GUVERCIN_RENK
    etiket = "Şahin toplantı" if skor > 0 else "Güvercin toplantı"

    for col_idx, ticker in enumerate(["^TNX", "DX-Y.NYB"], start=1):
        df = fiyat_cache.get(ticker)
        if df is None:
            continue
        pencere = olay_penceresi(df, row["tarih"])
        if pencere is None:
            continue
        offsetler = sorted(o for o in pencere if not np.isnan(pencere[o]))
        ref = pencere[-1]
        if ticker in GETIRI_TICKERLARI:
            y_degerler = [(pencere[o] - ref) * 100 for o in offsetler]
        else:
            y_degerler = [(pencere[o] - ref) / ref * 100 for o in offsetler]
        goster_legend = (skor > 0 and not sahin_gosterildi) or (skor <= 0 and not guvercin_gosterildi)
        fig4.add_trace(go.Scatter(
            x=offsetler, y=y_degerler, mode="lines+markers",
            line=dict(color=renk, width=1.8), marker=dict(size=5),
            name=etiket, legendgroup=etiket, showlegend=bool(goster_legend and col_idx == 1),
            opacity=0.75,
            hovertemplate=f"{row['tarih'].date()}<br>gün: %{{x}}<br>değişim: %{{y:+.2f}}<extra></extra>",
        ), row=1, col=col_idx)
        if col_idx == 1:
            if skor > 0:
                sahin_gosterildi = True
            else:
                guvercin_gosterildi = True

for c in (1, 2):
    fig4.add_vline(x=0, line_color=NOTR_GRI, line_width=1, line_dash="dot", row=1, col=c)
    fig4.add_hline(y=0, line_color=NOTR_GRI, line_width=0.8, row=1, col=c)
fig4.update_xaxes(title_text="Açıklamaya göre işlem günü (0 = açıklama günü)", row=1, col=1)
fig4.update_xaxes(title_text="Açıklamaya göre işlem günü (0 = açıklama günü)", row=1, col=2)
fig4.update_yaxes(title_text="Baz puan (referans: t-1 kapanışı)", row=1, col=1)
fig4.update_yaxes(title_text="% değişim (referans: t-1 kapanışı)", row=1, col=2)
fig4_tema = dict(ORTAK_TEMA)
fig4_tema["margin"] = dict(l=70, r=170, t=110, b=60)
fig4.update_layout(
    **fig4_tema,
    title=dict(
        text=f"Olay Penceresi — Açıklama Anı Etrafında ±{PENCERE_GUN} İşlem Günü "
             f"({len(gecmis_df)} toplantı üst üste bindirildi)",
    ),
    height=650,
    legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02),
)
kaydet(fig4, "04_olay_penceresi_faiz_dxy_hareketi", genislik=1550, yukseklik=650)

# --- Görsel 5: Tonlama x varlık ısı haritası ---------------------------------
pivot5 = olay_df.pivot_table(index="tarih", columns="varlik_adi", values="tepki_0g_yuzde", aggfunc="mean")
pivot5 = pivot5.sort_index()
z = pivot5.values
zmax_abs = np.nanmax(np.abs(z)) if np.any(~np.isnan(z)) else 1.0
fig5 = go.Figure(data=go.Heatmap(
    z=z, x=pivot5.columns, y=[t.strftime("%Y-%m-%d") for t in pivot5.index],
    colorscale=[[0, GUVERCIN_RENK], [0.5, "#f0efec"], [1, SAHIN_RENK]],
    zmid=0, zmin=-zmax_abs, zmax=zmax_abs,
    text=np.round(z, 2), texttemplate="%{text}%",
    colorbar=dict(title="Açıklama-günü<br>% değişim"),
    hovertemplate="%{y} · %{x}<br>%{z:+.3f}%<extra></extra>",
))
fig5.update_layout(
    **ORTAK_TEMA,
    title="Tonlama Dönemi x Varlık Isı Haritası<br>"
          "<sup>her hücre açıklama gününün kapanış-kapanışa % değişimi (karşılaştırılabilirlik için tüm varlıklar % biriminde)</sup>",
    height=560, yaxis=dict(title="Toplantı tarihi", type="category", autorange="reversed"),
)
kaydet(fig5, "05_tonlama_isi_haritasi_donem_varlik")

# --- Görsel 6: En şahin / en güvercin açıklamalar sıralaması ----------------
siralama_df = tonlama_df.sort_values("tonlama_skoru", ascending=True).reset_index(drop=True)
renkler_6 = [SAHIN_RENK if s > 0 else GUVERCIN_RENK for s in siralama_df["tonlama_skoru"]]
fig6 = go.Figure()
fig6.add_bar(
    x=siralama_df["tonlama_skoru"], y=[t.strftime("%Y-%m-%d") for t in siralama_df["tarih"]],
    orientation="h", marker_color=renkler_6,
    text=[f"{s:+.2f}" for s in siralama_df["tonlama_skoru"]], textposition="outside",
    hovertemplate="%{y}<br>Tonlama skoru: %{x:+.2f}<extra></extra>",
)
fig6.add_vline(x=0, line_color=NOTR_GRI, line_width=1)
fig6.update_layout(
    **ORTAK_TEMA,
    title="En Şahin -> En Güvercin FOMC Açıklamaları Sıralaması<br>"
          "<sup>kırmızı = net şahin (sıkılaştırma tonu ağır bastı) · mavi = net güvercin (gevşeme tonu ağır bastı)</sup>",
    xaxis_title="Tonlama skoru (binde)", yaxis_title="",
    yaxis=dict(type="category"),
    height=140 + 42 * len(siralama_df),
)
kaydet(fig6, "06_en_sahin_en_guvercin_siralama", yukseklik=140 + 42 * len(siralama_df))

# ---------------------------------------------------------------------------
# 7. ÖZET
# ---------------------------------------------------------------------------
print("\n" + "=" * 72)
print("TAMAMLANDI.")
print(f"Analiz edilen açıklama sayısı : {len(metinler)}/{len(gecmis_df) + len(basarisiz)}")
print(f"Şahin/güvercin korelasyonları  : {korelasyonlar}")
print(f"Görseller  -> {GORSEL_DIZIN}")
print(f"Veri       -> {VERI_DIZIN}")
print("=" * 72)
