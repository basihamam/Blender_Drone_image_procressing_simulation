
# Blender_Drone_image_procressing_simulation
 Blender ile TCP/IP üzerinden haberleşen Python ve OpenCV tabanlı otonom İHA yazılımıdır. HSV maskeleme ile kırmızı/mavi hedefleri bulur, logaritmik spiral çizerek alan tarar. Hala geliştirme aşamasında








v0.1
şu an sadece basit bir görüntü ve spiral çizme var her hangi gibi ek bir şey yok 

 Mavi kare yakalama opencv ile
 
<img width="854" height="480" alt="2026-06-26 13-28-30 (online-video-cutter com)" src="https://github.com/user-attachments/assets/053bee5d-0abd-42fd-8032-245b9fb7c874" />


Kırmızı kare yakalama opencv ile

<img width="854" height="480" alt="2026-06-26 13-28-30 (online-video-cutter com)(3)" src="https://github.com/user-attachments/assets/10a84236-032b-4dcf-87d4-5c5f163db69f" />

v0.2
tasrımda değişikliklere gidildi ve loglrla yazılar sağ ve sola alındı.
drone viewer ve haritaya eklemler yapılıdı, artık waypoint sistemi ile haritada istediğiniz gibi gezdirebilirsiniz 
harita görüntüsü alma çeşitli fonksiyonlarla çalışıyor elinizde Camera,Sun,blue,red ve Camera_map olduğu sürece hangi haritayı yüklerseniz yükleyin otomatik olarak haritanın way point noktasını çıkarabiliyor


<img width="854" height="480" alt="2026-07-02 13-23-38 (online-video-cutter com)" src="https://github.com/user-attachments/assets/59005585-9ebc-4907-aa1c-155795582c34" />


# DİKKAT kullanım hala son kullanıcılar için uygun değil drone başlatmak için tuşları kullanıyonuz haritayı açmak ve manuel waypoint ayarlamak için p tuşu , m tuşu ilede default bir şekilde spiral mi dönücek yoksa sizin manuel way pointtemi uçacak onu ayarlıyorsunuz, başlatmak için g tuşuna durdurmak için s tuşuna basmalısınız, bu arada manuel oluşturduğunuz yolda görüntü tanımlama çalışmıyor ve çalışması için koyduğum tuşu unuttum düzeltebilirim veya bu sorunları v0.3 de halledebilirim 

