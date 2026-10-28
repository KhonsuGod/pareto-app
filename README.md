# PROSES-MONITOR

CLI harian untuk monitoring downtime **PROSES 1** (Extrusion) dan
**PROSES 2** (Bolang): menarik data dari Google Sheet admin masing-masing
proses, perhitungan deterministic (tanpa AI), memperbarui workbook Excel
monitoring, dan membuat draft pesan WhatsApp dari angka aktual.

## 1. Setup

```
pip install -r requirements.txt
copy .env.example .env
```

`.env` opsional — ID spreadsheet kedua proses sudah tertulis di
`config.yaml` (`processes.proses1` / `processes.proses2`).

Buat template workbook (sekali saja per proses):

```
python app.py init --proses 1
python app.py init --proses 2
```

Template Proses 2 punya sheet lengkap
(RINGKASAN, DETAIL_DOWNTIME, REKAP_MESIN, PARETO_MESIN, PARETO_ISSUE,
TREND_HARIAN, PLUG_ASSIST, TUNGGU_BAHAN, FOLLOW_UP). Proses 1 tidak punya
PLUG_ASSIST / TUNGGU_BAHAN karena tidak relevan untuk extrusion
(diol lewat `workbook_optional` di config).

## 2. Akses Google Sheet

- **Default (tanpa API key)**: sheet admin dibaca via export publik
  `https://docs.google.com/spreadsheets/d/<ID>/export?format=xlsx`
  (sheet harus bisa dilihat oleh "anyone with the link").
  Unduhan dicache di `data/cache/` — bila offline, run terakhir dipakai.
- **Opsional (gspread)**: isi `GOOGLE_CREDENTIALS_FILE` dengan JSON
  service account dan set `google.fetcher: gspread` di `config.yaml`.

Credential tidak pernah di-hardcode; semua dari `.env` / `config.yaml`.

## 3. Jalankan harian

### Windows — cara paling gampang

Double-click **`Update_Harian.bat`**. Script itu otomatis memakai
Python 3.12 yang benar dan langsung membuka **menu interaktif**:

```
1. Update data Proses 2
2. Update data Proses 1
3. Lihat status
4. Buat draft pesan WhatsApp
5. Validasi workbook
6. Buka folder hasil
0. Keluar
```

Argumen tetap bisa dipakai lewat bat (misal `Update_Harian.bat status`).

### Lewat terminal

Kalau perintah `python` di komputer Anda diambil alih *Python Install Manager*
(muncul pesan `NoInstallsError: No runtimes are installed`), pakai path penuh:

```
%LOCALAPPDATA%\Programs\Python\Python312\python.exe app.py
```

atau:

```
py -3.12 app.py
```

> Muncul `'python' is not recognized`? Jendela cmd/PowerShell itu dibuka sebelum
> Python terpasang. Tutup semua jendela terminal, buka yang baru, lalu coba lagi.
> Catatan: `py` tanpa `-3.12` bisa memilih Python 3.15 yang belum punya
> dependensi — selalu pakai `py -3.12` atau path penuh.

### Daftar perintah

```
python app.py                                   # menu interaktif
python app.py update daily --proses 2           # tanggal terbaru yang belum diproses
python app.py update daily --proses 1 --latest  # paksa tanggal terbaru (upsert)
python app.py update daily --proses 1 --date 2026-10-27
python app.py draft --proses 2 --clip           # draft WhatsApp, salin ke clipboard
python app.py draft --proses 1 --date 2026-10-27
python app.py validate [--proses 1|2]
python app.py status [--proses 1|2]             # last processed / source / workbook
```

Simpan otomatis:

- Proses 2 → `data/output/Monitoring_Proses2_LATEST.xlsx` (+ dated + backups)
- Proses 1 → `data/output/proses1/Monitoring_Proses1_LATEST.xlsx` (+ dated + backups)

Mengulang tanggal yang sama tidak menimbulkan duplikat (baris tanggal lama
di-delete/replace, unique key = tgl+mesin+kode+jam mulai+jam selesai+keterangan).
`update daily` menampilkan `No new daily downtime data found.` kalau semua
tanggal source sudah pernah diproses.

## 4. Draft pesan WhatsApp

```
Update Pareto Proses 2 Pak @mr lukman cjm Di tanggal 27:

Downtime tertinggi ada di VACUM 7 = 180 menit, lanjut WM = 135 menit,
VACUM 8 = 120 menit, dan TFM 1 = 100 menit.

VACUM 7 banyak dari pisau, stacking, conveyor, dan bahan sambungan.
WM banyak dari alarm drives dan perbaikan evakuator rak b error.

Tolong dibantu follow up yang masih berulang.

CC Pak Dio
```

Semua angka dan nama penyebab berasal dari data workbook — tidak ada
kalimat template kosong. Penyebab mesin dicocokkan dari keterangan asli
pakai daftar keyword → frasa di `config.yaml` → `message.drivers`
(satu daftar per proses). Draft tersimpan sebagai
`Draft_WhatsApp_<Proses>_<tanggal>.txt` di folder output.

## 5. Validasi

Sebelum workbook disimpan, dicek otomatis: tanggal valid, menit numeric,
tidak ada duplicate event / duplicate daily update, total mesin = total
downtime harian, kontribusi Pareto ≈ 100%, kumulatif terakhir = 100%, dan
tidak ada `#REF!/#DIV/0!/#VALUE!/#N/A`.
**Jika gagal, workbook tidak disimpan dan LATEST tidak ditimpa.**

## 6. Konfigurasi

Semua yang sering berubah diatur lewat `config.yaml`:

- `processes.<key>` — spreadsheet ID, nama sheet, posisi header
  (Proses 1: baris 3, di atasnya ada legend), nama kolom, label kategori
  (`LT Maintenance → LT`), template & folder output, file state.
- `issue_mapping` — keyword → label issue per proses.
- `message` — format header draft, top mesin, frasa penyebab, closing, CC.
- `machine_grouping` — `TFM 1.1 → TFM 1`, nama asli tetap dipertahankan.
- `followup` — threshold P1/P2 per proses.

Keterangan asli (`description_raw`) dan nama mesin asli tidak pernah dibuang.
