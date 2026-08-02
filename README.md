# Fed Speak — Merkez Bankası Şahin/Güvercin Tonlama Analizi

Jerome Powell kürsüye çıktığında konuşma hızını bile piyasa okur. "Elevated" mı dedi "somewhat elevated" mi, "patient" mı "data-dependent" mi, tek bir sıfat değişikliği trilyon dolarlık piyasaları saniyeler içinde oynatabiliyor. "Too Big to Fail" filmini izleyenler hatırlar: kriz gecesi herkesin gözü ekranda, Fed'den çıkacak tek cümleyi bekliyordu. Bu proje tam olarak o cümleleri didikliyor. Son 10 FOMC açıklamasını kelime kelime tarayıp şahin mi (sıkılaştırma) güvercin mi (gevşeme) olduğuna bakıyor, sonra piyasanın o gün gerçekten nasıl tepki verdiğini ölçüyor.

## Ne yapıyor

Dört adım. federalreserve.gov'un resmi FOMC takvim sayfasından son 10 düzenli faiz kararı toplantısının basın açıklaması linklerini gerçekten scrape ediyor. Her açıklamanın tam metnini çekip finans-duyarlı bir şahin/güvercin kelime sözlüğüyle tarıyor, basit bir negasyon düzeltmesi ("not tightening" gibi cümleleri ters çevirme) uyguluyor. yfinance'ten gerçek piyasa verisiyle (10 yıllık ve 5 yıllık hazine getirisi, dolar endeksi, S&P 500) her açıklama tarihi etrafında ±3 işlem günlük bir olay penceresi kuruyor. Son olarak tonlama skorunun piyasa tepkisiyle gerçekten ilişkili olup olmadığını, küçük örneklemin izin verdiği ölçüde ve dürüstçe, test ediyor.

Proje tamamen anahtarsız: federalreserve.gov herkese açık metin, yfinance herkese açık piyasa verisi. Hiçbir API anahtarı gerekmiyor.

## Veri: dürüst durum

10/10 açıklama gerçekten çekildi. 2025-06-18'den 2026-07-29'a kadar 10 düzenli FOMC faiz kararı toplantısının basın açıklaması metni federalreserve.gov'dan indirildi, uydurulan tek bir cümle yok. Her metin `veri/fomc_metinleri/` altında ham haliyle duruyor, isteyen açıp karşılaştırabilir.

Takvim sayfasında 2025-08-22 tarihli bir "notation vote" da vardı (Statement on Longer-Run Goals and Monetary Policy Strategy oylaması), ama bu düzenli bir faiz kararı açıklaması değil, farklı bir belge türü. Bilinçli olarak listeye alınmadı.

Metinler kısa: 125-386 kelime arasında değişiyor, ortalama yaklaşık 290. FOMC açıklamaları zaten böyle, Fed kısa ve kalıp cümlelerle konuşur, asıl renk basın toplantısında ve tutanaklarda (minutes) çıkar. Bu proje sadece statement metnini kullandı, basın toplantısı transkriptini veya tutanakları kapsamıyor. Bu bilinçli bir kapsam sınırlaması, aşağıda tekrar not düşüyorum.

## Metodoloji

### Tonlama skoru

Önce açık söyleyeyim: bu bir finBERT ya da başka bir dil modeli sınıflandırması değil. Kelime frekansı tabanlı, basit ve açıklanabilir bir yöntem. Metinde şahin ifadeler (tighten, restrictive, hike, further increases, upside risks to inflation, somewhat elevated...) ile güvercin ifadeler (accommodative, patient, gradual, downside risks, ample, lower the target range...) sayılıyor, aradaki fark toplam kelime sayısına bölünüp binde cinsinden bir yoğunluk skoruna çevriliyor. Pozitif şahin ağır bastığını, negatif güvercin ağır bastığını gösteriyor.

Basit bir negasyon düzeltmesi de var: bir ifadenin hemen önündeki 6 kelimede "not/no/without/never" gibi bir olumsuzlama varsa kategori tersine çevriliyor. Bunun gerçekte işe yaradığı bir örnek 2026-04-29 açıklamasında çıktı. Bir üye "did not support inclusion of an easing bias in the statement" diyerek açıklamaya gevşeme yönlü bir ifade eklenmesine karşı çıktığını belirtmiş. "Easing" kelimesi tek başına güvercin sayılırdı ama "did not support" onu tersine çeviriyor, üye aslında daha şahin bir metin istemiş. Sistem bunu doğru yakaladı ve "easing"i şahin tarafına saydı.

Yöntemin kendi kendini düzelttiği bir an da oldu, onu da saklamıyorum. İlk taramada leksikonda "strongly committed" vardı, görev tarifindeki örneklerden esinlenerek eklenmişti. Sonuçları kontrol ederken 10 açıklamanın 8'inde "The Committee is strongly committed to supporting maximum employment and returning inflation to its 2 percent objective" cümlesinin birebir aynı olduğunu fark ettim. Bu FOMC şablonunun sabit bir paragrafı, tonlamayla hiçbir ilgisi yok, sadece o paragrafın o açıklamada kullanılıp kullanılmadığını ölçüyordu (iki kısa açıklamada kullanılmamıştı, muhtemelen format kısalığından). Gerçek bir sinyal değil, gürültüydü. Leksikondan çıkarıldı ve tüm sonuçlar yeniden hesaplandı. Bu değişiklik olmadan yayınlanan ilk versiyon yanıltıcı olurdu; bu README'deki tüm sayılar düzeltilmiş versiyona ait.

### Piyasa tepkisi

Her açıklama tarihi için en yakın işlem gününden ±3 işlem günü geriye/ileriye bakan bir pencere kuruluyor (takvim günü değil, işlem günü, hafta sonları/tatiller karıştırılmıyor). Getiri varlıklarında (10Y, 5Y) değişim baz puan cinsinden hesaplanıyor, çünkü zaten yüzde olarak kote edildikleri için fark direkt baz puan veriyor. DXY ve S&P 500'de yüzde değişim kullanılıyor. Karşılaştırılabilirlik gereken görsellerde (ısı haritası, scatter) tüm varlıklar ek olarak ortak bir yüzde-değişim biriminde de tutuluyor.

"2 yıllık getiri" için görev tarifinde önerilen proxy'lerden ^FVX (5 yıllık) seçildi, ^IRX (13 haftalık) değil, çünkü ^IRX zaten Fed'in mevcut politika faizine o kadar yakın sabitleniyor ki FOMC sürprizlerine görece durağan kalıyor. ^FVX orta vadeli patika beklentilerini daha iyi yansıtıyor. Gerçek 2 yıllık hazine getirisi yfinance'in ücretsiz kataloğunda yok.

En son iki toplantı (2026-06-17, 2026-07-29) için +3 günlük pencere bugüne göre henüz tam oluşmamıştı; o hücreler NaN bırakıldı, uydurulmadı. Toplam 40 açıklama x varlık kombinasyonundan 36'sında tam pencere mevcut.

## Bulgular

10 açıklamanın tonlama skoru -13.12 (2025-12-10, en güvercin) ile +3.42 (2025-06-18, en şahin) arasında değişti. Örneklemde sadece 1 toplantı net şahin çıktı, geri kalan 9'u nötr veya güvercin. Bu, dönemin genel olarak bir gevşeme/faiz indirimi döngüsü olmasıyla tutarlı: 2025 Eylül-Aralık arasında art arda indirimler yapıldı, dissent'lerin çoğu da daha fazla indirim isteyen üyelerden geldi.

Tonlama skoru ile açıklama-günü piyasa tepkisi arasındaki korelasyon (Pearson r, n=10):

| Varlık | r | Yorum |
|---|---|---|
| 10 Yıllık Hazine Getirisi | +0.11 | Pratikte ilişki yok |
| 5 Yıllık Hazine Getirisi (proxy) | -0.05 | Pratikte ilişki yok |
| Dolar Endeksi (DXY) | +0.05 | Pratikte ilişki yok |
| S&P 500 | -0.35 | Zayıf-orta, yön mantıklı (şahin → hisse düşüşü) ama n=10'da güvenilmez |

Dürüst sonuç: bu kelime-sözlüğü skoru, bu örneklemde piyasa tepkisiyle anlamlı bir ilişki göstermedi. En güçlü korelasyon bile (S&P 500, -0.35) n=10 ile istatistiksel olarak neredeyse hiçbir şey ispatlamıyor, güven aralığı o kadar geniş ki sıfırı rahatça içeriyor. Bunu "sistem çalışmıyor" diye süslemeden yazıyorum: 10 gözlemlik bir örneklemde hiçbir korelasyon iddiası ciddiye alınmamalı, ben de almıyorum.

Bunun birkaç muhtemel nedeni var. Birincisi örneklem küçüklüğü: 10 toplantı, istatistiksel gürültüden edge ayırt etmek için yeterli değil (bu projedeki diğer showcase'lerde de tekrarlanan bir ders: n<100 "geçti/kaldı" demek için yetersiz). İkincisi, piyasa açıklamayı önceden büyük ölçüde fiyatlıyor: FOMC kararları genelde sürpriz değil, asıl hareket beklentiyle gerçekleşen arasındaki farktan geliyor, ki bu proje o farkı ölçmüyor (beklenti verisi yok). Üçüncüsü, ve muhtemelen en büyüğü, kelime sözlüğü yöntemi gerçek dil anlayışından yoksun. Muhtemelen finBERT gibi bağlamı anlayan bir dil modeliyle çok daha iyi ayrışırdı. Bunu umut cümlesi olarak değil, bu projenin somut bir sınırlaması olarak yazıyorum.

## Görseller (`gorseller/`)

Her biri hem `.html` (etkileşimli) hem `.png` (statik). Kelime bulutu PNG-only, doğası gereği.

1. `01_zaman_icinde_tonlama_skoru`: 10 toplantının tonlama skoru zaman serisi, nötr bant ve sıfır çizgisiyle
2. `02_tonlama_vs_piyasa_tepkisi_scatter`: 4 varlık için küçük-çoklu scatter, her birinde eğim çizgisi ve Pearson r
3. `03_one_cikan_ifadeler_kelime_bulutu`: leksikonda gerçekten eşleşen ifadeler, kırmızı=şahin / mavi=güvercin, büyüklük=frekans
4. `04_olay_penceresi_faiz_dxy_hareketi`: 10 toplantı üst üste bindirilmiş, açıklama anı etrafında ±3 gün kümülatif hareket (10Y getiri + DXY)
5. `05_tonlama_isi_haritasi_donem_varlik`: her toplantı x her varlık için açıklama-günü % değişim ısı haritası
6. `06_en_sahin_en_guvercin_siralama`: 10 toplantının tonlama skoruna göre sıralanmış bar grafiği

## Sınırlamalar ve bilinçli kararlar

Bağlam ve ironi yakalanamıyor. Görev tarifinde verilen örnek hâlâ geçerli: "not tightening further" gibi bir cümlede negasyon penceresi kurtarıyor, ama daha incelikli bağlamsal kalıpları (alay, koşullu ifade, çok-cümlelik mantık) yakalayamıyor.

Aynı kelime farklı bağlamda farklı anlam taşıyabiliyor ve sözlük bunu ayırt edemiyor. Somut örnek: 2026-06-17 açıklamasında "Inflation remains elevated relative to the Committee's 2 percent goal" cümlesi var, okuyana oldukça şahin geliyor. Ama leksikon sadece tam "somewhat elevated" ifadesini arıyor, çünkü diğer açıklamalarda hep o kalıpla geçiyordu, bu yüzden bu cümle hiç yakalanmadı ve o toplantı sırf tek bir "ample" kelimesi yüzünden güvercin tarafına kaydı (-8.00). Sözlük tam ifade eşleştirmesi yaptığı için eş anlamlı ya da yakın varyasyonları kaçırıyor; yöntemin en somut zayıflığı bu.

Sınıf dengesizliği var: bu örneklemde 9/10 toplantı nötr veya güvercin, sadece 1/10 şahin. "Şahin toplantı" kategorisinin görsellerdeki (özellikle olay penceresi grafiğindeki) kırmızı çizgisi tek bir gözleme dayanıyor, bir eğilim değil, tek bir veri noktası olarak okunmalı.

Beklenti/sürpriz ekseni yok. Piyasa tepkisi açıklamanın mutlak tonuna değil, beklenenle gerçekleşen arasındaki farka duyarlıdır. Bu proje beklenti verisi (ör. Bloomberg/Refinitiv ekonomist anketleri) kullanmadı, dolayısıyla "şahin ama beklenenden az şahin" gibi durumları ayırt edemiyor.

Sadece statement metni işlendi, basın toplantısı ve tutanaklar hariç. Powell'ın soru-cevap kısmı genelde statement'tan daha fazla piyasa hareketi yaratır; bu projenin kapsamı bilinçli olarak sadece yazılı açıklamayla sınırlı tutuldu.

Leksikon MEDIUM güvenle derlendi: akademik ya da onaylı bir sözlük değil, görev tarifindeki örnekler ve alan bilgisiyle oluşturulmuş bir hipotez. "Strongly committed" örneğinde olduğu gibi boilerplate/gerçek-sinyal ayrımı elle kontrol edilerek düzeltildi, ama sözlüğün geri kalanında benzer gizli boilerplate kalıpları hâlâ olabilir.

## Kurulum ve çalıştırma

```bash
cd 50_fed_speak
../.venv/bin/python proje.py
```

Anahtar gerekmiyor. Çıktılar `gorseller/` ve `veri/` altına yazılır (ham statement metinleri `veri/fomc_metinleri/` altında).

## requirements.txt

```
requests==2.34.2
beautifulsoup4==4.15.0
lxml==6.1.1
pandas==3.0.5
numpy==2.4.6
plotly==6.9.0
kaleido==1.3.0
wordcloud==1.9.6
yfinance==1.5.2
```
