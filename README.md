# PROSES-MONITOR

CLI harian untuk Plant Bolang, satu aplikasi dua tool:

- **Tool 1 — Daily Production Monitoring**: monitoring downtime
  **PROSES 1** (Extrusion) dan **PROSES 2** (Bolang): menarik data dari
  Google Sheet admin masing-masing proses, perhitungan deterministic
  (tanpa AI), memperbarui workbook Excel monitoring, dan membuat draft
  pesan WhatsApp dari angka aktual.
- **Tool 2 — Tooling & Spare Monitoring**: stock sparepart, pengeluaran,
  opname, alarm, dan pareto pemakaian spare Proses 2, berbasis workbook
  `monitorung_spare_proses2.xlsx` (nama file asli, typo tetap dipakai).

Kedua tool independen: kalau satu gagal, yang lain tetap jalan.

## 1. Setup

```
pip install -r requirements.txt
copy .env.example .env     → isi ADMIN_SHEET_URL (Proses 2) & ADMIN_SHEET_URL_PROSES1
```

`.env` wajib — link sheet admin kedua proses hanya disimpan di situ
(tidak ada di `config.yaml`, dan `.env` tidak ikut ke git).

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
Python 3.12 yang benar dan langsung membuka **launcher dua tool**:

```
[1] DAILY PRODUCTION MONITORING   → submenu Tool 1:
    1. Update data Proses 2
    2. Update data Proses 1
    3. Lihat status produksi
    4. Buat draft pesan WhatsApp
    5. Validasi workbook
    6. Buka folder hasil
    0. Kembali ke launcher

[2] TOOLING & SPARE MONITORING    → submenu Tool 2 (lihat seksi 7)

[0] EXIT
```

Ada animasi ASCII startup ±1 detik. Untuk mematikannya:
`python app.py --no-animation`, atau set environment
`MONITOR_NO_ANIMATION` / `NO_COLOR`, atau jalankan lewat pipe/non-TTY
(animasi otomatis skip). Perintah langsung (mis. `update daily`) tidak
pernah menjalankan animasi.

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
python app.py                                   # launcher dua tool (animasi)
python app.py --no-animation                    # launcher, tanpa animasi
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

## 7. Tooling & Spare Monitoring (Tool 2)

Menu `python app.py` → `[2]`, atau perintah langsung:

```
python app.py tooling find BJ-PP00246-0    # lookup MASTER TOOLING (read-only)
python app.py spare status                 # status stock semua komponen
python app.py spare pareto month           # today / week / month / range
python app.py spare pareto --from 2026-10-01 --to 2026-10-29
python app.py spare history [--family F] [--component C]
python app.py spare daily [--date YYYY-MM-DD]
python app.py spare whatsapp [--clip]      # draft WhatsApp spare
python app.py spare opname                 # opname interaktif / bendera di bawah
python app.py spare opname --family DATAR-12 --component "PLUG ASSIST" --physical 4 --pic Davi --reason "count awal"
python app.py spare correlate              # indikator downtime vs spare (read-only)
```

Workbook: `data/spare/monitorung_spare_proses2.xlsx` — disalin otomatis dari
sumber asli (`Z:\davi\monitoring_sparepart\...`, read-only) saat pertama kali
dipakai. `MASTER TOOLING` tidak pernah diubah oleh transaksi; lookup bisa
menampilkan beberapa baris routing untuk satu Kode BJ, dan komponen `CEK TS`
ditandai **BELUM TERVERIFIKASI** (tidak direka).

## 8. Stock: cara kerja & setup opening stock

Stock dihitung oleh **formula Excel** (sumber kebenaran):

```
Stock Aktual (F) = Stock Awal (D) - SUMIFS(Qty Keluar di LOG PENGELUARAN)
Keluar Hari Ini (E) = SUMIFS(..., tanggal = TODAY())
```

Python tidak mengurangi stock dua kali — hanya menambah baris OUT ke log dan
mengisi Stock Awal saat opname. Konsekuensinya:

- **Stock kosong ≠ nol.** Baris dengan Stock Awal kosong berstatus
  `UNKNOWN` dan transaksi keluar diblok sampai opname pertama.
- `python app.py spare opname` pada item yang belum punya Stock Awal
  mencatat **OPENING** (baseline cutover) di sheet `LEDGER SPARE`;
  koreksi berikutnya tercatat sebagai **ADJUSTMENT** (stock sistem, fisik,
  selisih, PIC, alasan — riwayat tidak ditimpa).
- Minimum stock diisi sendiri di `config.yaml` → `spare.minimum_stock`
  (per family → komponen). Status: `OUT` (terverifikasi 0), `LOW`
  (≤ minimum terkonfigurasi), `OK`, `NOT CONFIGURED` (positif tanpa
  threshold), `DEFICIT` (negatif, hanya lewat override beralasan yang
  dicatat di ledger).
- Setiap transaksi punya ID unik (`T2-OUT-...` di kolom K log). Ulangi
  transaksi dengan ID sama tidak menduplikasi catatan (idempotent).

## 9. Backup & recovery

Sebelum setiap penyimpanan, workbook spare dibackup otomatis ke
`data/spare/backups/` (10 terakhir disimpan). Penyimpanan atomik: ditulis ke
file sementara, divalidasi, dibuka ulang untuk cek integritas, baru
menggantikan workbook utama — gagal validasi berarti workbook lama tidak
disentuh. Workbook sedang dibuka di Excel → proses berhenti dengan pesan
"Tutup workbook di Excel", coba lagi setelah file ditutup. Perubahan dari
luar aplikasi terdeteksi (checksum di `data/spare/state.json`).

Recovery manual: ambil backup terbaru dari `data/spare/backups/` dan salin
menimpa `data/spare/monitorung_spare_proses2.xlsx`.

## 10. Keterbatasan data (per akhir 2026-10-29)

- 112 dari 117 item stock **belum punya Stock Awal** → status `UNKNOWN`
  sampai opname. 5 item OVAL-14/OVAL-16 sudah terisi dari source (14/17).
- Semua log pengeluaran masih kosong → pareto & dashboard baru muncul
  setelah ada transaksi nyata (tidak ada data karangan).
- Threshold minimum stock belum ada satupun — wajib diisi user setelah
  stock terverifikasi.
- Banyak routing MASTER TOOLING masih `CEK TS` (belum diverifikasi TS).
- `DASHBOARD SPARE` dibuat lazy: baru dibuat setelah transaksi OUT pertama.
