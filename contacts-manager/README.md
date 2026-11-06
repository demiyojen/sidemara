# Rehber Yöneticisi (prototip)

iCloud Kişiler'i (iPhone rehberi) bilgisayardan yönetir. Yalnızca Python 3 gerekir.

1. appleid.apple.com → Oturum Açma ve Güvenlik → **Uygulamaya Özel Parolalar** ile parola oluştur.
2. `config.example.json` dosyasını `config.json` olarak kopyala ve doldur (git'e girmez).
3. `start.bat` (ya da `python server.py`) çalıştır; tarayıcı açılır: http://127.0.0.1:8765
4. Önce denemek için: `python server.py --demo` (iCloud'a bağlanmaz, `demo-data/` kullanır).

Her başlangıçta `backups/` klasörüne tam yedek yazılır. Gerçek iCloud'a karşı henüz test edilmedi.
Ayrıntılı geliştirme promptu: `CLAUDE_CODE_PROMPT.md`.
