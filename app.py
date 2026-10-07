from __future__ import annotations

import io
import json
import re
import threading
import uuid
import webbrowser
from datetime import datetime
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pymupdf as fitz  # PyMuPDF
from PIL import Image, ImageOps

# Fixed label size requested by the user: width 80 mm × height 60 mm.
MM_TO_PT = 72.0 / 25.4
PAGE_W = 80.0 * MM_TO_PT
PAGE_H = 60.0 * MM_TO_PT
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif"}
MAX_UPLOAD_BYTES = 250 * 1024 * 1024


PAGE_HTML = r'''<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>چاپ لیبل ۸۰ × ۶۰ | TSC</title>
  <style>
    :root { color-scheme: dark; --bg:#0a1020; --panel:#111a2e; --line:#24324d; --text:#eef4ff; --muted:#9eabc2; --cyan:#46dfc5; --blue:#7898ff; --red:#ff8787; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; color:var(--text); background:radial-gradient(ellipse at 10% 0%, #17304b 0, transparent 38%), radial-gradient(ellipse at 90% 10%, #222447 0, transparent 35%), var(--bg); font-family:Tahoma,"Segoe UI",Arial,sans-serif; }
    .wrap { width:min(920px, calc(100% - 32px)); margin:0 auto; padding:34px 0 48px; }
    .brand { display:flex; align-items:center; gap:10px; color:var(--cyan); font:700 12px/1.4 "Segoe UI",Arial,sans-serif; letter-spacing:.16em; direction:ltr; }
    .brand-mark { display:grid; place-items:center; width:30px; height:30px; border:1px solid #438d94; border-radius:9px; background:#123542; font-size:12px; }
    h1 { margin:23px 0 8px; font-size:clamp(25px, 4vw, 36px); line-height:1.35; letter-spacing:-.03em; }
    .lead { color:var(--muted); line-height:1.9; margin:0 0 23px; max-width:680px; font-size:15px; }
    .size-pill { display:inline-flex; align-items:center; gap:8px; padding:8px 13px; margin-bottom:20px; border:1px solid #2a665f; border-radius:999px; background:#102b2b; color:#b8fff0; font-size:13px; font-weight:700; }
    .size-pill span { direction:ltr; unicode-bidi:isolate; }
    .panel { background:linear-gradient(145deg, rgba(22,33,56,.96), rgba(15,24,42,.97)); border:1px solid var(--line); border-radius:20px; padding:22px; box-shadow:0 22px 70px rgba(0,0,0,.28); }
    .drop { min-height:165px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; gap:8px; padding:22px; border:1.5px dashed #3c5974; border-radius:15px; background:rgba(9,18,33,.5); cursor:pointer; transition:.18s ease; }
    .drop:hover, .drop.drag { border-color:var(--cyan); background:rgba(31,77,78,.2); transform:translateY(-1px); }
    .upload-icon { width:40px; height:40px; display:grid; place-items:center; border-radius:12px; background:#183c48; color:var(--cyan); font-size:22px; }
    .drop strong { font-size:16px; }
    .drop small { color:var(--muted); line-height:1.7; }
    input[type=file] { display:none; }
    .toolbar { display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between; margin:18px 0 10px; }
    .count { color:var(--muted); font-size:13px; }
    .text-btn { border:0; color:#b7c8e2; background:transparent; padding:8px 10px; cursor:pointer; font:inherit; font-size:13px; }
    .text-btn:hover { color:white; }
    .file-list { display:flex; flex-direction:column; gap:8px; margin:9px 0 17px; max-height:240px; overflow:auto; }
    .file-row { display:flex; align-items:center; justify-content:space-between; gap:12px; border:1px solid #293a56; background:#101a2d; border-radius:11px; padding:10px 12px; }
    .file-meta { min-width:0; }
    .file-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; direction:auto; }
    .file-size { margin-top:4px; color:var(--muted); font-size:11px; }
    .remove { flex:0 0 auto; width:30px; height:30px; border:1px solid #394660; border-radius:9px; background:transparent; color:#c3cce0; cursor:pointer; font-size:18px; }
    .remove:hover { border-color:var(--red); color:var(--red); }
    .primary { width:100%; display:flex; justify-content:center; align-items:center; gap:9px; min-height:50px; border:0; border-radius:12px; color:#062326; background:linear-gradient(110deg, #49e0c4, #82e7d0); font:700 15px Tahoma,"Segoe UI",sans-serif; cursor:pointer; box-shadow:0 8px 25px rgba(70,223,197,.13); transition:.15s ease; }
    .primary:hover:not(:disabled) { filter:brightness(1.05); transform:translateY(-1px); }
    .primary:disabled { opacity:.45; cursor:not-allowed; box-shadow:none; }
    .note { display:flex; gap:11px; margin-top:16px; padding:13px 14px; border:1px solid #594c32; border-radius:12px; background:rgba(65,49,19,.2); color:#e9d7ae; font-size:12px; line-height:1.9; }
    .note b { color:#ffe7a5; white-space:nowrap; }
    .result { margin-top:16px; padding:17px; border:1px solid #286454; border-radius:14px; background:rgba(18,63,52,.28); }
    .result h2 { margin:0 0 6px; color:#b7ffdf; font-size:17px; }
    .result p { margin:4px 0 12px; color:#c1d8d3; font-size:13px; line-height:1.8; }
    .result-actions { display:flex; flex-wrap:wrap; gap:9px; }
    .result a { display:inline-flex; align-items:center; justify-content:center; min-height:39px; padding:8px 13px; border-radius:9px; text-decoration:none; font-size:13px; font-weight:700; }
    .open-pdf { color:#052522; background:var(--cyan); }
    .download-pdf { color:#e7efff; background:#243652; border:1px solid #435677; }
    .warning { margin-top:10px !important; color:#ffdda0 !important; white-space:pre-wrap; }
    .error { margin-top:14px; padding:12px 14px; border:1px solid #713c48; border-radius:10px; background:rgba(96,31,46,.25); color:#ffc5cd; font-size:13px; line-height:1.8; white-space:pre-wrap; }
    .foot { margin-top:17px; color:#7888a3; font-size:11px; text-align:center; }
    @media(max-width:580px) { .wrap{padding-top:23px}.panel{padding:15px}.drop{min-height:145px}.note{display:block}.note b{display:block;margin-bottom:3px} }
  </style>
</head>
<body>
  <main class="wrap">
    <div class="brand"><span class="brand-mark">TSC</span><span>LOCAL LABEL PRINT</span></div>
    <h1>آماده‌سازی و چاپ لیبل</h1>
    <p class="lead">فایل‌های PDF یا تصویر را انتخاب کنید. هر صفحهٔ PDF یا هر تصویر، به یک لیبل جدا تبدیل می‌شود و محتوای هرکدام متناسب با اندازهٔ صفحه، بدون کشیدگی یا برش، وسط‌چین خواهد شد.</p>
    <div class="size-pill">اندازهٔ خروجی: <span>80 × 60 mm</span></div>

    <section class="panel">
      <label class="drop" id="dropZone" for="fileInput">
        <span class="upload-icon">＋</span>
        <strong>برای انتخاب فایل کلیک کنید یا فایل‌ها را اینجا بکشید</strong>
        <small>PDF، JPG، PNG، BMP، TIFF، WEBP یا GIF · انتخاب چند فایل مجاز است</small>
      </label>
      <input id="fileInput" type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.bmp,.tif,.tiff,.webp,.gif,application/pdf,image/*">

      <div class="toolbar">
        <span class="count" id="countText">هنوز فایلی انتخاب نشده</span>
        <button class="text-btn" id="clearBtn" type="button">پاک‌کردن فهرست</button>
      </div>
      <div class="file-list" id="fileList"></div>
      <button class="primary" id="makeBtn" type="button" disabled><span>ساخت PDF آمادهٔ چاپ</span><span aria-hidden="true">←</span></button>
      <div id="errorBox" class="error" hidden></div>
      <div id="resultBox" class="result" hidden>
        <h2 id="resultTitle">PDF آماده شد</h2>
        <p id="resultText"></p>
        <div class="result-actions">
          <a class="open-pdf" id="openPdf" target="_blank" rel="noopener">بازکردن PDF برای چاپ</a>
          <a class="download-pdf" id="downloadPdf">دانلود PDF</a>
        </div>
        <p class="warning" id="warningText" hidden></p>
      </div>
      <div class="note"><b>تنظیم چاپ مهم است</b><span>در پنجرهٔ چاپ، پرینتر TSC را انتخاب کنید؛ اندازهٔ کاغذ/لیبل باید ۸۰×۶۰ میلی‌متر باشد و مقیاس روی Actual size یا 100% قرار بگیرد، نه Fit. اگر امکانش هست حاشیه‌ها را None بگذارید. درایور پرینتر نیز باید روی نوع لیبل و سنسور Gap تنظیم شده باشد.</span></div>
    </section>
    <div class="foot">این برنامه روی همین کامپیوتر اجرا می‌شود؛ فایل‌ها برای سرویس آنلاین ارسال نمی‌شوند.</div>
  </main>
  <script>
    const input = document.getElementById('fileInput');
    const zone = document.getElementById('dropZone');
    const list = document.getElementById('fileList');
    const count = document.getElementById('countText');
    const makeBtn = document.getElementById('makeBtn');
    const clearBtn = document.getElementById('clearBtn');
    const errorBox = document.getElementById('errorBox');
    const resultBox = document.getElementById('resultBox');
    let files = [];
    const supported = /\.(pdf|png|jpe?g|bmp|tiff?|webp|gif)$/i;
    function formatBytes(n) {
      if (n < 1024) return n + ' B';
      if (n < 1024*1024) return (n/1024).toFixed(1) + ' KB';
      return (n/(1024*1024)).toFixed(1) + ' MB';
    }
    function addFiles(incoming) {
      const rejected = [];
      for (const f of incoming) {
        if (!supported.test(f.name)) { rejected.push(f.name); continue; }
        const duplicate = files.some(x => x.name === f.name && x.size === f.size && x.lastModified === f.lastModified);
        if (!duplicate) files.push(f);
      }
      render();
      if (rejected.length) showError('این نوع فایل پشتیبانی نمی‌شود:\n' + rejected.join('\n'));
    }
    function render() {
      list.replaceChildren();
      files.forEach((f, i) => {
        const row = document.createElement('div'); row.className = 'file-row';
        const meta = document.createElement('div'); meta.className = 'file-meta';
        const name = document.createElement('div'); name.className = 'file-name'; name.textContent = f.name;
        const size = document.createElement('div'); size.className = 'file-size'; size.textContent = formatBytes(f.size);
        meta.append(name, size);
        const del = document.createElement('button'); del.className = 'remove'; del.type = 'button'; del.textContent = '×'; del.title = 'حذف فایل';
        del.addEventListener('click', () => { files.splice(i,1); render(); });
        row.append(meta, del); list.append(row);
      });
      count.textContent = files.length ? `${files.length} فایل انتخاب شده` : 'هنوز فایلی انتخاب نشده';
      makeBtn.disabled = files.length === 0;
      resultBox.hidden = true;
      errorBox.hidden = true;
    }
    function showError(text) { errorBox.textContent = text; errorBox.hidden = false; }
    input.addEventListener('change', () => { addFiles(Array.from(input.files || [])); input.value = ''; });
    clearBtn.addEventListener('click', () => { files = []; render(); });
    for (const name of ['dragenter','dragover']) zone.addEventListener(name, e => { e.preventDefault(); zone.classList.add('drag'); });
    for (const name of ['dragleave','drop']) zone.addEventListener(name, e => { e.preventDefault(); zone.classList.remove('drag'); });
    zone.addEventListener('drop', e => addFiles(Array.from(e.dataTransfer.files || [])));
    makeBtn.addEventListener('click', async () => {
      if (!files.length) return;
      errorBox.hidden = true; resultBox.hidden = true;
      makeBtn.disabled = true; makeBtn.querySelector('span').textContent = 'در حال آماده‌سازی…';
      const form = new FormData(); files.forEach(f => form.append('files', f, f.name));
      try {
        const response = await fetch('/make', { method:'POST', body:form });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || 'ساخت فایل ناموفق بود.');
        document.getElementById('resultTitle').textContent = `PDF آماده شد · ${data.pages} لیبل`;
        document.getElementById('resultText').textContent = `فایل «${data.filename}» ساخته شد. برای چاپ، PDF را باز کنید و از پنجرهٔ چاپ، پرینتر TSC را انتخاب کنید.`;
        const open = document.getElementById('openPdf'); open.href = data.pdf_url;
        document.getElementById('downloadPdf').href = data.download_url;
        if (data.warnings && data.warnings.length) {
          const w = document.getElementById('warningText'); w.textContent = 'این فایل‌ها پردازش نشدند:\n' + data.warnings.join('\n'); w.hidden = false;
        } else { document.getElementById('warningText').hidden = true; }
        resultBox.hidden = false;
      } catch (err) {
        showError(err.message || 'ارتباط با برنامه برقرار نشد. صفحه را تازه‌سازی و دوباره امتحان کنید.');
      } finally {
        makeBtn.disabled = files.length === 0;
        makeBtn.querySelector('span').textContent = 'ساخت PDF آمادهٔ چاپ';
      }
    });
  </script>
</body>
</html>'''


def safe_basename(filename: str) -> str:
    # Avoid using a client-supplied path as a filesystem path.
    name = (filename or "file").replace("\\", "/").rsplit("/", 1)[-1]
    return name[:220] or "file"


def extract_multipart_files(content_type: str, body: bytes) -> list[tuple[str, bytes]]:
    raw = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("latin-1", errors="replace")
        + body
    )
    message = BytesParser(policy=policy.default).parsebytes(raw)
    if not message.is_multipart():
        raise ValueError("فرمت درخواست فایل‌ها قابل‌خواندن نیست.")

    uploaded: list[tuple[str, bytes]] = []
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        field_name = part.get_param("name", header="content-disposition")
        if field_name != "files":
            continue
        filename = safe_basename(part.get_filename() or "")
        data = part.get_payload(decode=True) or b""
        if not data:
            continue
        uploaded.append((filename, data))
    return uploaded


def _new_label_page(out_doc: fitz.Document) -> fitz.Page:
    page = out_doc.new_page(width=PAGE_W, height=PAGE_H)
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1), overlay=False)
    return page


def _insert_image_label(out_doc: fitz.Document, raw: bytes, filename: str) -> int:
    count = 0
    with Image.open(io.BytesIO(raw)) as source:
        frames = int(getattr(source, "n_frames", 1))
        for frame_no in range(frames):
            source.seek(frame_no)
            frame = ImageOps.exif_transpose(source.copy())
            if frame.width <= 0 or frame.height <= 0:
                continue

            # Flatten transparency onto white so the label stock remains white.
            if frame.mode in ("RGBA", "LA") or (frame.mode == "P" and "transparency" in frame.info):
                rgba = frame.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, (255, 255, 255))
                rgb.paste(rgba, mask=rgba.getchannel("A"))
            else:
                rgb = frame.convert("RGB")

            image_stream = io.BytesIO()
            rgb.save(image_stream, format="PNG", optimize=True)
            image_bytes = image_stream.getvalue()
            scale = min(PAGE_W / rgb.width, PAGE_H / rgb.height)
            width = rgb.width * scale
            height = rgb.height * scale
            x0 = (PAGE_W - width) / 2
            y0 = (PAGE_H - height) / 2
            page = _new_label_page(out_doc)
            page.insert_image(fitz.Rect(x0, y0, x0 + width, y0 + height), stream=image_bytes)
            count += 1
    return count


def make_print_pdf(uploaded: list[tuple[str, bytes]]) -> tuple[Path, int, list[str]]:
    out_doc = fitz.open()
    errors: list[str] = []
    pages_added = 0

    for filename, data in uploaded:
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            errors.append(f"{filename}: نوع فایل پشتیبانی نمی‌شود")
            continue
        try:
            if suffix == ".pdf":
                src_doc = fitz.open(stream=data, filetype="pdf")
                try:
                    if src_doc.needs_pass:
                        raise ValueError("فایل PDF رمزگذاری شده است")
                    if src_doc.page_count == 0:
                        raise ValueError("فایل PDF صفحه‌ای ندارد")
                    for page_index in range(src_doc.page_count):
                        target = _new_label_page(out_doc)
                        target.show_pdf_page(target.rect, src_doc, page_index, keep_proportion=True, overlay=True)
                        pages_added += 1
                finally:
                    src_doc.close()
            else:
                added = _insert_image_label(out_doc, data, filename)
                if added == 0:
                    raise ValueError("تصویری برای چاپ پیدا نشد")
                pages_added += added
        except Exception as exc:
            errors.append(f"{filename}: {str(exc) or exc.__class__.__name__}")

    if pages_added == 0:
        out_doc.close()
        details = "\n".join(errors) if errors else "فایل قابل‌پردازشی انتخاب نشده است."
        raise ValueError("هیچ لیبلی ساخته نشد.\n" + details)

    docs = Path.home() / "Documents"
    try:
        docs.mkdir(parents=True, exist_ok=True)
        output_dir = docs / "TSC_LabelPrint"
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        output_dir = Path(__file__).resolve().parent / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"TSC_80x60_{stamp}_{uuid.uuid4().hex[:6]}.pdf"
    out_doc.set_metadata({
        "title": "TSC label sheet 80 x 60 mm",
        "author": "TSC 80x60 Label Print",
        "subject": f"{pages_added} label(s), page size 80 x 60 mm",
    })
    out_doc.save(str(output_path), garbage=4, deflate=True)
    out_doc.close()
    return output_path, pages_added, errors


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler):
        super().__init__(address, handler)
        self.jobs: dict[str, Path] = {}


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "TSCLabelPrint/1.0"

    def log_message(self, fmt, *args):
        # Keep the console quiet; the app is intended for everyday desktop use.
        return

    def _send(self, status: int, content_type: str, payload: bytes, headers: dict[str, str] | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, obj: dict):
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", payload)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._send(200, "text/html; charset=utf-8", PAGE_HTML.encode("utf-8"))
            return

        match = re.fullmatch(r"/(pdf|download)/([0-9a-f]{32})", path)
        if match:
            mode, job_id = match.groups()
            file_path = self.server.jobs.get(job_id)
            if not file_path or not file_path.is_file():
                self._send(404, "text/plain; charset=utf-8", "فایل پیدا نشد یا برنامه بسته شده است.".encode("utf-8"))
                return
            try:
                payload = file_path.read_bytes()
            except OSError:
                self._send(500, "text/plain; charset=utf-8", "خواندن PDF ناموفق بود.".encode("utf-8"))
                return
            disposition = "inline" if mode == "pdf" else "attachment"
            self._send(
                200,
                "application/pdf",
                payload,
                {"Content-Disposition": f'{disposition}; filename="{file_path.name}"'},
            )
            return

        self._send(404, "text/plain; charset=utf-8", b"Not found")

    def do_POST(self):
        if urlparse(self.path).path != "/make":
            self._json(404, {"ok": False, "error": "مسیر پیدا نشد."})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"ok": False, "error": "اندازهٔ فایل ارسالی نامعتبر است."})
            return
        if content_length <= 0:
            self._json(400, {"ok": False, "error": "لطفاً دست‌کم یک فایل انتخاب کنید."})
            return
        if content_length > MAX_UPLOAD_BYTES:
            self._json(413, {"ok": False, "error": "مجموع فایل‌ها از حد ۲۵۰ مگابایت بیشتر است."})
            return

        try:
            body = self.rfile.read(content_length)
            uploaded = extract_multipart_files(self.headers.get("Content-Type", ""), body)
            if not uploaded:
                raise ValueError("فایلی دریافت نشد. لطفاً دوباره فایل‌ها را انتخاب کنید.")
            output_path, pages, errors = make_print_pdf(uploaded)
            job_id = uuid.uuid4().hex
            self.server.jobs[job_id] = output_path
            self._json(200, {
                "ok": True,
                "pages": pages,
                "filename": output_path.name,
                "pdf_url": f"/pdf/{job_id}",
                "download_url": f"/download/{job_id}",
                "warnings": errors,
            })
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._json(500, {"ok": False, "error": f"خطای غیرمنتظره: {str(exc) or exc.__class__.__name__}"})


def main() -> None:
    server = AppServer(("127.0.0.1", 0), RequestHandler)
    host, port = server.server_address
    url = f"http://{host}:{port}/"
    print("TSC Label Print آماده است.")
    print(f"در حال بازکردن برنامه در مرورگر: {url}")
    print("برای بستن برنامه، این پنجره را ببندید یا Ctrl+C بزنید.")
    threading.Timer(0.5, lambda: webbrowser.open(url, new=2)).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        print("برنامه بسته شد.")


if __name__ == "__main__":
    main()
