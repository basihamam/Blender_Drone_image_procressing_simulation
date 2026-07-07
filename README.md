# Blender Drone Image Processing Simulation

Blender ortamı ile TCP/IP protokolü üzerinden gerçek zamanlı haberleşen, Python ve OpenCV tabanlı bir otonom İHA (İnsansız Hava Aracı) yazılımı simülasyonudur. Sistem, HSV maskeleme algoritmalarıyla kırmızı ve mavi renkli hedefleri dinamik olarak tespit eder ve logaritmik spiral çizerek otonom alan taraması gerçekleştirir. Projenin geliştirme süreci aktif olarak devam etmektedir.

---

## 🚀 Sürüm Geçmişi ve Özellikler

### 📍 v0.1 — Temel Altyapı ve Renk Maskeleme
* **Görüntü Aktarımı:** Blender üzerindeki kamera görüntüsü TCP/IP soket haberleşmesi üzerinden Python tarafına başarıyla aktarıldı.
* **Otonom Arama:** İHA için temel seviyede logaritmik spiral arama rotası mekanizması entegre edildi.
* **Görüntü İşleme:** OpenCV kullanılarak kamera akışındaki mavi ve kırmızı kare hedeflerin başarıyla yakalanması sağlandı.

#### Mavi Kare Yakalama (OpenCV)
<img width="854" height="480" alt="Mavi Kare Yakalama" src="https://github.com/user-attachments/assets/053bee5d-0abd-42fd-8032-245b9fb7c874" />

#### Kırmızı Kare Yakalama (OpenCV)
<img width="854" height="480" alt="Kırmızı Kare Yakalama" src="https://github.com/user-attachments/assets/10a84236-032b-4dcf-87d4-5c5f163db69f" />

---

### 📍 v0.2 — Arayüz Yenilemesi ve Dinamik Waypoint Sistemi
* **Arayüz (UI) Düzenlemesi:** Telemetri verileri ve log yazıları, görüşü kapatmayacak şekilde ekranın sağ ve sol panellerine taşındı.
* **Gelişmiş Göstergeler:** Drone Viewer (İHA Kamerası) ve taktik harita ekranı sisteme eklendi.
* **Akıllı Harita Analitiği:** Sahnede `Camera`, `Sun`, `blue`, `red` ve `Camera_map` nesneleri bulunduğu sürece, sisteme hangi harita yüklenirse yüklensin otomatik olarak haritanın Waypoint (rota noktası) sınırları çıkarılabilmektedir.
* **Waypoint Navigasyonu:** Kullanıcıların harita üzerinde manuel rota noktaları oluşturarak İHA'yı istedikleri gibi uçurabilmelerine olanak tanındı.

<img width="854" height="480" alt="v0.2 Harita ve Waypoint Sistemi" src="https://github.com/user-attachments/assets/59005585-9ebc-4907-aa1c-155795582c34" />

> 🟥 **Önemli Eksiklik:** Şu anki sürümde, kullanıcı tarafından manuel olarak oluşturulan rotalarda otonom görüntü işleme/hedef tanımlama özelliği çalışmamaktadır. Bu sorunun v0.3 sürümünde tamamen çözülmesi planlanmaktadır.

---

### 📍 v0.3 — Genişletilmiş Harita ve Rota Editörü
* **Büyük Ölçekli Harita:** Önceki sürüme kıyasla **4 kat daha büyük** yeni bir operasyon haritası entegre edildi.
* **Tarama ve Optimizasyon:** Harita tarama algoritmalarındaki hatalar (scan errors) düzeltildi, waypoint aksiyonları optimize edildi.
* **Görsel Geliştirmeler:** Waypoint noktalarına durumsal renk kodları eklendi.
* **İnteraktif Rota Yönetimi:** Rota noktalarını harita üzerinde doğrudan sürükleyip bırakma (drag-and-drop), araya yeni waypoint ekleme ve mevcut noktaları silebilme özellikleri eklendi.

<img width="854" height="480" alt="v0.3 Gelişmiş Rota Editörü" src="https://github.com/user-attachments/assets/5c818277-2771-4b9b-be3a-9425701a91d7" />

---

## <span style="color:red">⚠️ DİKKAT: KULLANIM NOTLARI VE BİLİNEN SINIRLILIKLAR</span>

**Yazılım henüz son kullanıcı aşamasında (kararlı sürümde) değildir ve geliştirme ortamı tuş kombinasyonları ile kontrol edilmektedir:**

* **`P` Tuşu:** Harita ekranını açar ve manuel rota noktası (waypoint) belirleme modunu aktif eder.
* **`K` Tuşu:** tıklanınca konulan default actionu değiştirir
* **`b` Tuşu:** dümdüz çizgiler yerine eğri çizgileri aktif eder
* **`h` Tuşu:** görev haritasını açar
* **`M` Tuşu:** Uçuş modunu değiştirir (İHA'nın varsayılan otonom spiral rotada mı yoksa sizin belirlediğiniz manuel rotada mı uçacağını ayarlar).
* **`G` Tuşu:** İHA uçuş görevini başlatır (Start).
* **`S` Tuşu:** İHA uçuş görevini durdurur (Stop).

