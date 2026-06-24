---
name: too-music-expert
description: Expert instructions explaining how the Too Music Discord voice/music bot operates, including commands, events, and troubleshooting.
---

# Panduan Ahli: Cara Kerja Bot Discord "Too Music"

Dokumen ini adalah profil Skill yang dirancang untuk AI Agent guna memahami, mengelola, memodifikasi, dan mendebug bot Discord **Too Music** di repositori ini secara mendalam.

---

## 1. Arsitektur & Teknologi Utama
Bot Discord "Too Music" adalah bot pemutar musik voice channel yang berjalan di atas teknologi berikut:
- **Pustaka Core**: `discord.py` (versi v2.x) dengan ekstensi suara (`discord.py[voice]`).
- **Pencarian & Parser**: `yt-dlp` untuk mengekstrak informasi streaming audio langsung dari YouTube secara realtime tanpa mengunduh file fisik.
- **Audio Engine**: `FFmpeg` untuk mengalirkan audio format raw stream ke Voice Channel Discord.
- **Konfigurasi**: `.env` untuk memuat token Discord (`DISCORD_TOKEN`) dan jalur executables FFmpeg (`FFMPEG_PATH`).

---

## 2. Kelas Manajer Antrean (`MusicQueue`)
Logika antrean lagu per server Discord dikelola di dalam memori RAM menggunakan class [MusicQueue](file:///c:/experiment/discord-bot/bot.py#L51):
- **Struktur Penyimpanan**: Dictionary global `queues` memetakan ID server (`guild_id`) ke objek `MusicQueue` masing-masing menggunakan fungsi [get_queue](file:///c:/experiment/discord-bot/bot.py#L85).
- **Atribut**:
  - `self.queue`: List berisi dictionary lagu yang akan diputar berikutnya.
  - `self.current`: Dictionary lagu yang sedang diputar saat ini.
  - `self.loop`: Boolean untuk mengulang satu lagu yang sedang aktif saja.
  - `self.loop_queue`: Boolean untuk memasukkan kembali lagu yang baru selesai diputar ke bagian akhir daftar antrean.
- **Metode Kunci**:
  - `add(song)`: Menambahkan lagu ke dalam list `self.queue`.
  - `next()`: Mengembalikan lagu berikutnya untuk diputar berdasarkan status loop aktif.
  - `clear()`: Menghapus antrean, meriset status loop, dan membersihkan data lagu saat ini.

---

## 3. Alur Kerja Pemutaran Audio Asynchronous
Proses pemutaran audio dirancang agar efisien dan non-blocking:
1. **Pencarian Musik**: Fungsi [search_song](file:///c:/experiment/discord-bot/bot.py#L128) menggunakan `yt-dlp` berjalan di dalam thread pool executor melalui `loop.run_in_executor(None, search_song, query)`. Langkah ini memastikan pencarian web tidak membekukan (block) event loop utama Discord bot.
2. **Menyiapkan Audio Source**: Audio disalurkan lewat `discord.FFmpegPCMAudio` menggunakan opsi reconnect:
   `-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5`.
   Audio kemudian dibungkus dalam `discord.PCMVolumeTransformer` dengan volume default `0.5` (50%).
3. **Playback & Loop Callback**:
   Fungsi [play_next](file:///c:/experiment/discord-bot/bot.py#L178) bertindak sebagai pengatur giliran lagu berikutnya. Saat memanggil `voice_client.play()`, bot mendaftarkan callback `after=after_playing` yang secara otomatis memanggil kembali `play_next()` ketika lagu berakhir (atau di-skip), menciptakan rantai putar otomatis sampai antrean kosong.

---

## 4. Siklus Sinkronisasi Command & Event
- **Ready Event (`on_ready`)**:
  Saat bot online, event [on_ready](file:///c:/experiment/discord-bot/bot.py#L204) dipicu. Di sini, bot melakukan pendaftaran ulang slash command secara instan ke seluruh guild server yang terhubung menggunakan `bot.tree.copy_global_to` dan `bot.tree.sync(guild=guild)`. Langkah ini mempercepat munculnya perintah slash command di aplikasi Discord klien pengguna.

---

## 5. Spesifikasi Lengkap Slash Commands

| Nama Command | Parameter | Cara Kerja Internal |
|---|---|---|
| `/tjoin` | *Tidak ada* | Memeriksa apakah pengguna ada di Voice Channel (VC). Jika ya, hubungkan bot ke VC tersebut. Jika bot sudah berada di VC lain, pindahkan bot ke VC pengguna. |
| `/tplay` | `query` (String) | Memicu pencarian audio YouTube. Jika bot belum join VC, otomatis memanggil logika join. Menambahkan lagu ke antrean. Jika bot idle, pemicu pemutaran langsung dijalankan. |
| `/tskip` | *Tidak ada* | Mematikan status `music_queue.loop` sementara, kemudian mengeksekusi `voice_client.stop()`. Hal ini memicu callback `after` untuk langsung memainkan lagu berikutnya di antrean. |
| `/tstop` | *Tidak ada* | Memanggil `music_queue.clear()`, kemudian menyetop pemutaran audio aktif dengan `voice_client.stop()`. |
| `/tloop` | `mode` (Choices: song/queue/off) | Mengubah atribut boolean `loop` atau `loop_queue` pada objek antrean server tersebut. |
| `/tqueue` | *Tidak ada* | Mengambil 10 antrean teratas, menjumlahkan total durasi lagu di antrean, merender teks embed status, dan menampilkan panel informasi di bawah embed. |
| `/tnowplaying` | *Tidak ada* | Menampilkan informasi rinci lagu aktif. Menghitung persentase detik lagu berjalan dibanding durasi total, kemudian merender progress bar menggunakan fungsi [make_progress_bar](file:///c:/experiment/discord-bot/bot.py#L119). |
| `/tleave` | *Tidak ada* | Memanggil `music_queue.clear()`, memutuskan koneksi suara melalui `voice_client.disconnect()`, dan melepaskan resource audio. |

---

## 6. Pola Penanganan Masalah & Troubleshooting
Jika terjadi kendala pada bot, periksa poin-poin berikut:
- **Izin Saluran Suara (Voice Permissions)**:
  Bot memerlukan izin `Connect` dan `Speak` di voice channel tempat pengguna berada. Jika gagal, exception ditangkap dan dikembalikan sebagai pesan kesalahan berwarna merah.
- **Ketersediaan Engine FFmpeg**:
  Audio streaming tidak akan berfungsi jika binary `ffmpeg` tidak terinstall di sistem operasi. Pada deploy awan (seperti Render), parameter build command harus menyertakan `apt-get install -y ffmpeg` (lihat berkas [render.yaml](file:///c:/experiment/discord-bot/render.yaml)).
- **Lagu Buffering/Macet**:
  Parameter input di `FFMPEG_OPTIONS` dikonfigurasi untuk menangani reconnecting otomatis. Jika audio macet karena masalah jaringan YouTube, opsi ini membantu bot menyambung kembali stream secara background tanpa memutuskan sambungan VC.
