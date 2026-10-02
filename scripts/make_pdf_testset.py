"""Public PDF test set for Phase 3 (no real documents).

  spec_en.pdf / spec_ja.pdf            2-page technical specification: headings, styled text, bullets, table
  spec_en_scanned.pdf / spec_ja_...    the same pages as images only (200 dpi, scanner-like noise)
  slides_en.pdf                        sample_en.pptx exported by PowerPoint (if PowerPoint is installed)
  protected.pdf                        password-protected copy of spec_en.pdf
  corrupt.pdf                          truncated file
"""
from __future__ import annotations

import io
import subprocess
from pathlib import Path

import numpy as np
import pymupdf

OUT = Path(__file__).resolve().parent.parent / "eval" / "testset"
FONTS = r"C:\Windows\Fonts"

SPEC = {
    "en": """
<h1>BMS Integration Specification</h1>
<p class="sub">Smart Building Platform — Revision 2.1, 15 March 2026</p>
<h2>1. Scope</h2>
<p>This document specifies the integration of the <b>Building Management System (BMS)</b> with the cloud
platform. The BMS monitors and controls HVAC equipment, lighting and power meters in the building.</p>
<h2>2. System Components</h2>
<ul>
<li>Air Handling Unit (AHU) controllers, model <b>FX-PCG2611-0</b></li>
<li>Variable Air Volume (VAV) terminal controllers</li>
<li>Occupancy sensors and CO2 sensors (0–2,000 ppm)</li>
<li>Edge device and gateway (BACnet/IP, Modbus TCP, MQTT)</li>
</ul>
<h2>3. Network Requirements</h2>
<table>
<tr><th>Item</th><th>Value</th></tr>
<tr><td>BMS server</td><td>192.168.1.100</td></tr>
<tr><td>BACnet/IP port</td><td>47808</td></tr>
<tr><td>MQTT broker</td><td>mqtt.example.com:8883</td></tr>
<tr><td>Polling interval</td><td>15 minutes</td></tr>
</table>
<h2>4. Alarm Handling</h2>
<p>When a chiller alarm occurs, the system notifies the maintenance team by e-mail (support@example.com) and
creates a work order. If the alarm is not acknowledged within 30 minutes, it is escalated to the facility
manager.</p>
<p class="note"><b>Note:</b> Setpoint changes require operator approval.</p>
<h2 style="page-break-before: always">5. Energy Management</h2>
<p>The Energy Management System (EMS) records energy consumption every 15 minutes. Peak demand was reduced by
18% in summer 2025 through demand response and a cooling setpoint adjustment from 24 °C to 26 °C.</p>
<h2>6. Data Retention</h2>
<p>Trend log data is stored for 13 months in the cloud platform at https://bms.example.com/trends.</p>
""",
    "ja": """
<h1>BMS統合仕様書</h1>
<p class="sub">スマートビルディングプラットフォーム — 改訂2.1、2026年3月15日</p>
<h2>1. 適用範囲</h2>
<p>本書は、<b>ビル管理システム（BMS）</b>とクラウドプラットフォームとの統合について規定する。BMSは建物内の空調設備、照明および電力量計を監視・制御する。</p>
<h2>2. システム構成</h2>
<ul>
<li>空調機（AHU）コントローラー、型式 <b>FX-PCG2611-0</b></li>
<li>可変風量（VAV）ターミナルコントローラー</li>
<li>在室センサーおよびCO2センサー（0～2,000 ppm）</li>
<li>エッジデバイスおよびゲートウェイ（BACnet/IP、Modbus TCP、MQTT）</li>
</ul>
<h2>3. ネットワーク要件</h2>
<table>
<tr><th>項目</th><th>値</th></tr>
<tr><td>BMSサーバー</td><td>192.168.1.100</td></tr>
<tr><td>BACnet/IPポート</td><td>47808</td></tr>
<tr><td>MQTTブローカー</td><td>mqtt.example.com:8883</td></tr>
<tr><td>ポーリング間隔</td><td>15分</td></tr>
</table>
<h2>4. 警報処理</h2>
<p>冷凍機の警報が発生すると、システムは保守チームにメール（support@example.com）で通知し、作業指示を作成する。30分以内に警報が確認されない場合は、施設管理者にエスカレーションする。</p>
<p class="note"><b>注記：</b>設定値の変更にはオペレーターの承認が必要である。</p>
<h2 style="page-break-before: always">5. エネルギー管理</h2>
<p>エネルギー管理システム（EMS）は15分ごとにエネルギー消費量を記録する。2025年夏には、デマンドレスポンスおよび冷房設定値の24 °Cから26 °Cへの変更により、ピーク需要を18%削減した。</p>
<h2>6. データ保持</h2>
<p>トレンドログのデータは、クラウドプラットフォーム（https://bms.example.com/trends）に13か月間保存される。</p>
""",
}

CSS = """
@font-face {font-family: body; src: url(%(regular)s);}
@font-face {font-family: body; src: url(%(bold)s); font-weight: bold;}
* {font-family: body; font-size: 10.5px; line-height: 1.35;}
h1 {font-size: 20px; color: #1f4e9a; margin-bottom: 2px;}
h2 {font-size: 13px; color: #1f4e9a; margin-top: 12px; margin-bottom: 4px;}
p.sub {font-size: 10px; color: #555555;}
p.note {color: #c01f1f;}
table {border-collapse: collapse; margin-top: 4px;}
td, th {border: 1px solid #888888; padding: 3px 8px; text-align: left;}
th {background-color: #dde6f3;}
"""


def build_spec(lang: str, path: Path) -> None:
    fonts = {"en": ("arial.ttf", "arialbd.ttf"), "ja": ("meiryo.ttc", "meiryob.ttc")}[lang]
    story = pymupdf.Story(html=SPEC[lang], user_css=CSS % {"regular": fonts[0], "bold": fonts[1]},
                          archive=pymupdf.Archive(FONTS))
    raw = io.BytesIO()                             # build in memory: the writer holds file locks on Windows
    writer = pymupdf.DocumentWriter(raw)
    page_rect = pymupdf.paper_rect("a4")
    content = page_rect + (60, 60, -60, -70)
    more = True
    while more:
        device = writer.begin_page(page_rect)
        more, _ = story.place(content)
        story.draw(device)
        writer.end_page()
    writer.close()
    doc = pymupdf.open(stream=raw.getvalue())      # footer with page numbers (a real document has them)
    for i, page in enumerate(doc, start=1):
        page.insert_text((page.rect.width / 2 - 10, page.rect.height - 35), f"{i} / {doc.page_count}",
                         fontsize=8, fontname="helv")
    doc.subset_fonts()                             # embed only the characters used (CJK fonts are large)
    doc.save(path, garbage=3, deflate=True)
    doc.close()


def scan(src: Path, dst: Path, seed: int = 7) -> None:
    """Image-only copy: 200 dpi greyscale, light noise and slight blur like a scanner."""
    rng = np.random.default_rng(seed)
    out = pymupdf.open()
    with pymupdf.open(src) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).astype(np.int16)
            arr = arr + rng.normal(0, 6, arr.shape).astype(np.int16)
            arr[:-1] = (arr[:-1] * 3 + arr[1:]) // 4                   # slight vertical blur
            arr = np.clip(arr, 0, 255).astype(np.uint8)
            img = pymupdf.Pixmap(pymupdf.csGRAY, pix.width, pix.height, arr.tobytes(), False)
            new = out.new_page(width=page.rect.width, height=page.rect.height)
            new.insert_image(new.rect, pixmap=img)
    out.save(dst, deflate=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for lang in ("en", "ja"):
        build_spec(lang, OUT / f"spec_{lang}.pdf")
        scan(OUT / f"spec_{lang}.pdf", OUT / f"spec_{lang}_scanned.pdf")
    with pymupdf.open(OUT / "spec_en.pdf") as doc:
        doc.save(OUT / "protected.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    data = (OUT / "spec_en.pdf").read_bytes()
    (OUT / "corrupt.pdf").write_bytes(data[: len(data) // 3])
    pptx = OUT / "sample_en.pptx"
    ps1 = Path(__file__).with_name("export_pdf.ps1")
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1), "-Pptx",
                        str(pptx), "-Pdf", str(OUT / "slides_en.pdf")], check=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        print("PowerPoint not available: slides_en.pdf not created")
    print("PDF test set written to", OUT)


if __name__ == "__main__":
    main()
