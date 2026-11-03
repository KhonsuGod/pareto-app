"""Kirim draft ke grup WhatsApp lewat WhatsApp Web (automation).

Cara kerja:
- Browser (Edge/Chrome) dibuka dengan profile terpisah khusus app
  (data/wa_profile) — sesi login WA Web tersimpan di situ, seperti
  WA Desktop: sekali scan QR, berikutnya otomatis login lagi.
- App mencari grup by name, mengetik draft (multiline aman, tanpa
  Enter di tengah), meng-attach gambar chart (opsional), lalu kirim.
- Selalu ada konfirmasi manusia sebelum kirim (di level CLI/menu).

Ini automation unofficial terhadap web client — tampilan WhatsApp Web
bisa berubah; semua langkah punya pesan error yang jelas supaya bisa
kirim manual lewat draft tersimpan.
"""
from __future__ import annotations

import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WA_URL = "https://web.whatsapp.com/"

# Selectors dengan fallback — tampilan WA Web kadang berubah.
SEARCH_SELECTORS = (
    'div[contenteditable="true"][data-tab="3"]',
    'div[contenteditable="true"][data-tab="4"]',
)
MSGBOX_SELECTORS = (
    'footer div[contenteditable="true"]',
    'div[contenteditable="true"][data-tab="10"]',
    'div[contenteditable="true"][data-tab="6"]',
)
ATTACH_SELECTORS = (
    'span[data-icon="plus"]',
    'span[data-icon="clip"]',
    'button[aria-label="Attach"]',
    'div[title="Attach"]',
    'div[title="Lampirkan"]',
)
FILE_INPUT_SELECTORS = (
    'input[type="file"][accept*="image"]',
    'input[type="file"]',
)


class WaError(RuntimeError):
    """Error kirim WA dengan pesan yang bisa ditindaklanjuti."""


def wa_settings(cfg: dict) -> dict:
    ws = cfg.get("whatsapp") or {}
    profile = Path(ws.get("browser_profile", "data/wa_profile"))
    if not profile.is_absolute():
        profile = ROOT / profile
    return {
        "groups": ws.get("groups") or {},
        "channel": ws.get("browser_channel", "msedge"),
        "profile": profile,
        "attach_chart": bool(ws.get("attach_chart", True)),
        "open_timeout": int(ws.get("open_timeout", 120)),
        "send_timeout": int(ws.get("send_timeout", 45)),
    }


def group_for(cfg: dict, key: str | None = None) -> str:
    """Nama grup untuk proses tertentu. Error jelas kalau belum dikonfigurasi."""
    s = wa_settings(cfg)
    key = key or cfg.get("process_key") or "proses2"
    name = (s["groups"] or {}).get(key) or ""
    if not name:
        raise WaError(
            f"Nama grup WhatsApp untuk '{key}' belum diisi.\n"
            f"       Isi di config.yaml: whatsapp.groups.{key}")
    return name


def _css_str(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _first_visible(page, selectors, timeout_ms: int):
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    return loc
            except Exception:
                continue
        time.sleep(0.3)
    return None


def is_logged(page) -> bool:
    try:
        for sel in ('#side', SEARCH_SELECTORS[0]):
            if page.locator(sel).count():
                return True
    except Exception:
        pass
    return False


def is_qr_screen(page) -> bool:
    try:
        if page.locator("canvas").count():
            return True
        content = page.content().casefold()
        for kw in ("scan the qr", "scan kode qr", "log in to whatsapp", "gunakan whatsapp"):
            if kw in content:
                return True
    except Exception:
        pass
    return False


def _launch(cfg):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise WaError("Playwright belum terpasang. Jalankan: pip install playwright") from exc
    s = wa_settings(cfg)
    s["profile"].mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    try:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(s["profile"]),
            channel=s["channel"],
            headless=False,  # WA Web tidak jalan di headless
            args=["--no-first-run", "--disable-blink-features=AutomationControlled"],
        )
    except Exception as exc:
        pw.stop()
        raise WaError(f"Gagal membuka browser ({s['channel']}): {exc}") from exc
    return pw, ctx


def _shutdown(pw, ctx) -> None:
    try:
        ctx.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass


def wait_ready(page, open_timeout: int) -> None:
    """Tunggu WA Web siap. Layar QR = jangan lanjut (butuh scan manusia)."""
    deadline = time.time() + open_timeout
    while time.time() < deadline:
        if is_logged(page):
            return
        if is_qr_screen(page):
            raise WaError(
                "WhatsApp Web belum login (layar QR terdeteksi).\n"
                "       Jalankan `python app.py wa login` sekali, scan QR-nya,\n"
                "       sesi tersimpan — berikutnya tidak perlu scan lagi.")
        time.sleep(1.0)
    raise WaError("WhatsApp Web tidak kunjung siap. Cek koneksi, lalu coba lagi.")


def open_for_login(cfg, max_wait: int = 600) -> None:
    """Sekali saja: buka WA Web supaya user bisa scan QR; tunggu sampai login."""
    s = wa_settings(cfg)
    pw, ctx = _launch(cfg)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto(WA_URL, wait_until="domcontentloaded")
    except Exception:
        pass
    print("  Jendela browser WA Web terbuka.")
    print("  Scan QR-nya dari HP (WhatsApp > Perangkat Tertaut).")
    print("  JANGAN tutup jendela browser sampai disuruh.")
    deadline = time.time() + max(max_wait, s["open_timeout"])
    while time.time() < deadline:
        if is_logged(page):
            print("  [OK] Login berhasil. Sesi tersimpan di profile app —")
            print("       berikutnya kirim tidak perlu scan lagi. Browser akan ditutup.")
            time.sleep(2)
            _shutdown(pw, ctx)
            return
        time.sleep(2)
    _shutdown(pw, ctx)
    raise WaError("Belum login dalam batas waktu. Coba lagi: python app.py wa login")


def _open_chat(page, group_name: str, timeout_s: int) -> None:
    search = _first_visible(page, SEARCH_SELECTORS, timeout_s * 1000)
    if search is None:
        raise WaError(
            "Kolom pencarian WhatsApp Web tidak ditemukan (kemungkinan tampilan berubah).\n"
            "       Kirim manual dulu lewat draft yang tersimpan.")
    search.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    page.keyboard.type(group_name, delay=40)

    t = _css_str(group_name)
    row = _first_visible(page, (
        f'span[title="{t}"]',
        f'[role="listitem"] span[title="{t}"]',
    ), 8000)
    if row is None:
        items = page.locator('[role="listitem"]')
        try:
            n = items.count()
        except Exception:
            n = 0
        for i in range(n):
            try:
                if group_name.casefold() in (items.nth(i).inner_text() or "").casefold():
                    row = items.nth(i)
                    break
            except Exception:
                continue
    if row is None:
        raise WaError(
            f"Grup '{group_name}' tidak ditemukan di daftar chat.\n"
            f"       Cek nama grup di config.yaml (whatsapp.groups) — harus sama persis.")
    row.click()
    time.sleep(1.0)


def _verify_sent(page, text: str) -> bool:
    """Cek ringan: baris pertama draft muncul di chat. Tidak 100% pasti."""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return False
    snippet = lines[0][:30]
    try:
        page.wait_for_function(
            "sel => document.body.innerText.includes(sel)", arg=snippet, timeout=6000)
        return True
    except Exception:
        return False


def send_to_group(cfg: dict, *, group_name: str, text: str,
                  image: Path | str | None = None) -> dict:
    """Buka WA Web, buka chat grup, kirim teks (+ gambar opsional)."""
    s = wa_settings(cfg)
    if not text or not text.strip():
        raise WaError("Pesan kosong — tidak ada yang dikirim.")
    if image is not None:
        image = Path(image)
        if not image.exists():
            raise WaError(f"File gambar tidak ada: {image}")
    pw, ctx = _launch(cfg)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(WA_URL, wait_until="domcontentloaded")
        except Exception:
            pass
        wait_ready(page, s["open_timeout"])
        _open_chat(page, group_name, s["send_timeout"])
        _type_and_send(page, text, image, s["send_timeout"])
        return {
            "group": group_name,
            "image": str(image) if image else None,
            "verified": _verify_sent(page, text),
        }
    finally:
        time.sleep(1.5)  # kasih waktu WA Web flush pesan sebelum browser ditutup
        _shutdown(pw, ctx)


def _type_and_send(page, text: str, image: Path | None, timeout_s: int) -> None:
    """Attach gambar dulu (kalau ada), ketik teks/caption, lalu Enter."""
    if image is not None:
        attach = _first_visible(page, ATTACH_SELECTORS, 6000)
        if attach is None:
            raise WaError(
                "Tombol lampir tidak ditemukan (tampilan WhatsApp Web mungkin berubah).\n"
                "       Kirim manual dulu lewat draft tersimpan, atau set whatsapp.attach_chart: false.")
        attach.click()
        file_input = _first_visible(page, FILE_INPUT_SELECTORS, 6000)
        if file_input is None:
            raise WaError("Input file tidak muncul setelah klik lampir.")
        file_input.set_input_file(str(image))
        caption = _first_visible(page, MSGBOX_SELECTORS, timeout_s * 1000)
        if caption is None:
            raise WaError("Kotak caption tidak muncul setelah pilih gambar.")
        caption.click()
        # insert_text: multiline masuk utuh TANPA memicu Enter/kirim
        page.keyboard.insert_text(text)
        page.keyboard.press("Enter")
        return

    box = _first_visible(page, MSGBOX_SELECTORS, timeout_s * 1000)
    if box is None:
        raise WaError("Kotak pesan tidak ditemukan — chat grup belum terbuka?")
    box.click()
    page.keyboard.insert_text(text)
    page.keyboard.press("Enter")
