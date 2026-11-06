# Claude Code'a verilecek prompt

> Aşağıdaki bloğu olduğu gibi Claude Code'a yapıştır. Çalışma dizini: bu repo, `contacts-manager/` klasörü.

````text
Rol: Kıdemli bir yazılım mühendisisin. `contacts-manager/` içindeki mevcut prototipi, iPhone rehberimi (iCloud Kişiler)
bilgisayardan eksiksiz yönetebileceğim, güvenilir, tam özellikli bir uygulamaya dönüştür. Önce kodu oku
(vcard.py, stores.py, server.py, static/index.html), sonra mevcut yapıyı bozmadan genişlet.

## Bağlam
- Windows 11 kullanıyorum, iPhone 13. Rehberde ~1000 kayıt var; iCloud Kişiler senkronu açık.
- iOS rehbere USB/Wi‑Fi ile doğrudan erişim vermez. Tek yol iCloud CardDAV: https://contacts.icloud.com
  (Apple ID + appleid.apple.com'dan alınmış UYGULAMAYA ÖZEL PAROLA, Basic auth). Burada yaptığım her değişiklik
  iCloud'a yazılır, telefona senkronla gelir.
- Mevcut prototip: Python 3 standart kütüphane (ek paket yok), 127.0.0.1'de yerel sunucu + tek sayfa vanilla JS arayüz.
  Demo modu (`python server.py --demo`) iCloud'suz `demo-data/` klasörüyle çalışır. Gerçek iCloud'a karşı TEST EDİLMEDİ;
  bunu ilk işin olarak doğrula (aşağıda "Gerçek iCloud doğrulaması").
- Arayüz dili Türkçe. Kod/yorumlar İngilizce olabilir.

## Hedef
Bir kişi kartındaki (vCard 3.0, iCloud'un kullandığı biçim) TÜM bilgileri görebilmeli, ekleyebilmeli, düzenleyebilmeli ve
silebilmeliyim; 1000+ kaydı toplu yönetebilmeliyim. Hiçbir bilinmeyen/desteklenmeyen alan düzenleme sırasında kaybolmamalı.

## 1) Kişi kartı alanları (hepsi düzenlenebilir)
- Ad: ön ek (Dr./Sayın), ad, ikinci ad, soyad, son ek, takma ad (NICKNAME), fonetik ad/soyad
  (X-PHONETIC-FIRST-NAME / X-PHONETIC-LAST-NAME), "Şirket olarak göster" (X-ABShowAs:COMPANY).
- İş: şirket, departman (ORG ikinci bileşen), unvan (TITLE), meslek (ROLE).
- Telefonlar (çoklu): etiket (Cep, iPhone, Ev, İş, Ana, İş Faksı, Ev Faksı, Çağrı cihazı, Diğer + ÖZEL etiket).
- E‑postalar (çoklu): etiket (Ev, İş, iCloud, Diğer + özel).
- URL'ler (çoklu), sosyal profiller (X-SOCIALPROFILE: Twitter/Facebook/LinkedIn/… ), anlık mesaj (IMPP / X-AIM,
  X-JABBER … → modern eşleniği).
- Adresler (çoklu): ADR = posta kutusu;uzantı;cadde;şehir;bölge;posta kodu;ülke + etiket (Ev/İş/Diğer/özel).
- Tarihler: doğum günü (BDAY, YILSIZ biçim `1604-MM-DD` / `--MM-DD` desteği — iCloud yılsız doğum gününü böyle saklar),
  diğer tarihler (item grubu + X-ABDATE + X-ABLabel: Yıldönümü vb.).
- İlişkili kişiler (X-ABRELATEDNAMES: Eş, Anne, Baba, Kardeş, Çocuk, Asistan, Yönetici, Arkadaş, özel).
- Not (çok satırlı), fotoğraf (PHOTO; yükleme, kırpma, yeniden boyutlandırma ~400px JPEG, silme, PNG/HEIC dönüşümü
  tarayıcıda canvas ile), zil sesi/mesaj sesi gibi bilinmeyen alanlar DOKUNULMADAN korunur.
- Etiket yönetimi: iCloud, `item1.TEL` + `item1.X-ABLabel:_$!<Mobile>!$_` biçimiyle etiket yazar. Standart etiketleri
  (`_$!<Mobile>!$_`, `_$!<Home>!$_`, `_$!<Work>!$_`, `_$!<Other>!$_`, …) doğru oku/yaz; özel etiketi düz metin yaz.
  Mevcut prototip yalnızca `TYPE=` parametresine bakıyor — bunu item‑group + X-ABLabel desteğiyle genişlet.
- Satır katlama (75 bayt), UTF‑8 (Türkçe karakterler), kaçış (`\, \; \n`), QUOTED-PRINTABLE/CHARSET gibi eski biçimleri okuma.
- Kart modeli: ham satırları sakla; sadece kullanıcının değiştirdiği alanları yeniden yaz. Round‑trip testi:
  parse → serialize → parse eşit olmalı; bilinmeyen satırlar korunmalı.

## 2) Liste ve toplu işlemler
- 1000+ kayıtta akıcı arayüz (sanal liste ya da sayfalama), A–Z harf atlama çubuğu, sıralama (ad/soyad/şirket/son değişiklik).
- Arama: ad, telefon (boşluk/+90/0 farkını yok sayarak), e‑posta, şirket, not; tüm alanlarda.
- Filtreler: isimsiz, telefonsuz, e‑postasız, fotoğrafsız, boş kart, bir gruba üye / hiçbir gruba üye değil,
  yalnız şirket, yinelenen telefon, geçersiz telefon biçimi.
- Çoklu seçim (Shift+tık aralık seçimi, Ctrl+A), toplu: sil, gruba ekle/çıkar, şirket/etiket değiştir,
  telefonları standart biçime çevir (örn. 05xx → +90 5xx), boşlukları temizle, ad büyük/küçük harf düzelt (Türkçe `İ/ı` doğru).
- Silme: onay penceresi + "son silinenler" yerel çöp kutusu (silinen kartın vCard'ı `trash/` içine yazılır), GERİ AL
  (Ctrl+Z) en az son toplu işlem için. Toplu işlem öncesi dry‑run özeti ("37 kayıt silinecek, ilk 10: …").
- Yinelenenleri bulma: aynı normalize telefon, aynı e‑posta, aynı/benzer isim (Türkçe karakter ve büyük/küçük harf duyarsız,
  basit benzerlik eşiği). Birleştirme önizlemesi: alan alan seç, çakışmada kullanıcı karar versin. Grup üyelikleri taşınmalı.

## 3) Gruplar
- iCloud grupları = `X-ADDRESSBOOKSERVER-KIND:group` kartları + `X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:<UID>` satırları.
- Grup oluştur / yeniden adlandır / sil (üyeleri silmeden), üye ekle/çıkar (sürükle‑bırak ve toplu seçim), bir kişinin
  tüm gruplarını kart içinde göster/düzenle. Kişi silinince tüm gruplardan temizle (prototip yapıyor; test ekle).

## 4) İçe / dışa aktarma ve yedek
- Başlangıçta otomatik tam yedek (`backups/*.vcf`); manuel "şimdi yedekle"; yedeğin tamamını/seçilen kayıtları .vcf ve .csv
  (Google/Outlook uyumlu sütunlar) olarak dışa aktar.
- .vcf içe aktar (çoklu kart) ve .csv içe aktar (sütun eşleme arayüzü); içe aktarırken yinelenenleri uyar.
- "Yedekten geri yükle" (seçili kayıtlar) — ama önce fark gösterimi.

## 5) Senkron ve dayanıklılık (en kritik kısım)
- Her kayıt için ETag sakla; PUT/DELETE'te `If-Match` kullan. 412 gelirse kullanıcıya "kayıt telefonda değişmiş" göster,
  kartı yeniden çekip farkı sun; sessizce üzerine yazma.
- Periyodik arka plan yenileme: `sync-collection` REPORT (RFC 6578) varsa onu, yoksa ETag listesi (PROPFIND getetag) ile
  yalnız değişenleri çek. Arayüzde "son eşitleme" zamanı ve manuel yenile. Telefonda yapılan değişiklikler birkaç saniye–dakika
  içinde yansımalı (gerçek zamanlı garanti yok; bunu arayüzde dürüstçe belirt).
- iCloud'un partition yönlendirmeleri (pXX-contacts.icloud.com), 207 Multi-Status ayrıştırma, 429/5xx için üstel geri çekilme,
  zaman aşımı, kimlik doğrulama hataları (401) için anlaşılır Türkçe mesaj. Toplu işlemleri kısmi başarısızlıkta raporla
  ("212 başarılı, 3 başarısız: …"), yarım kalan işlemi devam ettirilebilir yap.
- Tüm yazmalar tek bir iş kuyruğunda sıralı; aynı anda iki değişiklik çakışmasın. Sunucu kilitleri ve istek zaman aşımı.

## 6) Güvenlik ve gizlilik
- Sunucu SADECE 127.0.0.1'e bağlanır; Host/Origin kontrolü (DNS‑rebinding ve başka site isteklerine karşı) korunsun,
  ayrıca her oturum için rastgele bir API token'ı üret, sayfaya gömülü olarak ver, tüm /api isteklerinde iste.
- Apple ID ve uygulama parolası asla arayüzde, günlükte, hata mesajında veya git'te görünmesin. `config.json` .gitignore'da;
  mümkünse parolayı Windows Credential Manager'a koy (ek paket gerekiyorsa: `keyring`, opsiyonel; yoksa config.json'a düş).
- vCard içeriğini arayüze koyarken asla innerHTML kullanma (XSS); kişi alanları güvenilmeyen veridir.
- Hiçbir telemetri, harici CDN, harici istek yok (yalnızca iCloud CardDAV).

## 7) Arayüz
- Üç bölme: sol (Tüm kişiler / Gruplar / Yinelenenler / Çöp / Filtreler), orta (liste), sağ (seçili kartın tam editörü; modal yerine
  yan panel). Klavye kısayolları (/ ara, N yeni, Del sil, Ctrl+S kaydet, Esc kapat, ↑↓ gezin).
- Kaydedilmemiş değişiklik uyarısı, alan doğrulama (telefon/e‑posta biçimi), kaydetme durumu ("Kaydediliyor… / iCloud'a yazıldı").
- Açık/koyu tema, Türkçe sıralama (`Intl.Collator('tr')`), erişilebilir etiketler, dar ekranda çalışır.
- Fotoğraf: sürükle‑bırak yükleme, kare kırpma aracı (yakınlaştır/kaydır), önizleme, toplu "fotoğrafsızlar" görünümü.

## 8) Windows ve kurulum
- `start.bat` (çift tıkla: Python kontrolü, sunucuyu başlat, tarayıcıyı aç) ve `README.md` (Türkçe): Python kurulumu,
  uygulamaya özel parola alma adımları (appleid.apple.com → Oturum Açma ve Güvenlik → Uygulamaya Özel Parolalar),
  `config.json` örneği (`config.example.json`), ilk çalıştırma, yedek/geri yükleme, sorun giderme (401, 2FA, boş liste).
- Windows yol/satır sonu/UTF‑8 sorunlarına dikkat (open(..., encoding='utf-8', newline='')); konsol çıktısında Türkçe karakter.
- Ek bağımlılık eklemeden önce gerekçe yaz; varsayılan: yalnızca Python standart kütüphanesi.

## 9) Test ve doğrulama (zorunlu)
- `tests/` altında `unittest` testleri: vCard parse/serialize round‑trip (iCloud örnek kartları: etiketli telefonlar, item grupları,
  yılsız doğum günü, özel etiket, katlanmış satırlar, fotoğraf, grup kartı), telefon normalizasyonu, yinelenen bulma,
  birleştirme, grup üyeliği, toplu işlem dry‑run, ETag çakışması (FolderStore ve sahte CardDAV sunucusu ile).
- Yerel sahte CardDAV sunucusu yaz (http.server; PROPFIND/REPORT/PUT/DELETE, 207, ETag, If‑Match, 301 yönlendirme) ve
  CardDAVStore'u buna karşı test et.
- Arayüzü Playwright ile (yüklü) demo modunda uçtan uca dene: ara, düzenle, foto yükle, grupla, sil‑geri al, birleştir.
  Ekran görüntüsü al ve kontrol et. Testler geçmeden "bitti" deme; geçmeyeni açıkça raporla.

## Gerçek iCloud doğrulaması (ilk iş, ben yardım edeceğim)
1. Sana config.json'u ben dolduracağım (parolayı sohbete yazmayacağım). `python server.py` ile bağlan; yalnızca OKUMA ile
   kişi sayısını ve birkaç kartın ham vCard'ını (telefon/e‑posta/fotoğraf bayt içeriği maskelenmiş) bana göster.
2. Gerçek kartlarda gördüğün tüm farklı biçimleri (etiket kodlamaları, PHOTO biçimi, grup kartları) testlere örnek olarak ekle.
3. Yazma testini YALNIZCA oluşturduğun bir "TEST‑SİL" kartı üzerinde yap: oluştur → telefonda göründüğünü bana doğrulat →
   düzenle → sil. Gerçek kayıtlara ben onay vermeden toplu yazma/silme yapma.

## Çalışma kuralları
- Önce kısa bir plan çıkar, sonra küçük adımlarla ilerle; her adım sonunda testleri çalıştır ve commit at.
- Mevcut demo modu ve `FolderStore` çalışmaya devam etsin (offline/yedek kullanımı için).
- Silme/üzerine yazma gibi geri dönüşü zor işlemlerde varsayılan güvenli davranış: yedek + onay + geri alma.
- Bitirince: yapılanların, bilinen sınırların (iCloud gecikmesi, doğrulanamayan kısımlar) ve kullanım adımlarının özeti.
````

## Notlar
- Önce `python server.py --demo` ile arayüzü dene, sonra gerçek iCloud'a bağlan.
- Prompt, gerçek iCloud'a karşı yazma testini bilerek tek bir test kartıyla sınırlıyor; 1000 kaydı riske atmamak için.
