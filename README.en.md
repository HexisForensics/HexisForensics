🌐 **English** · [Português](README.md) · [Español](README.es.md)

<p align="center"><img src="assets/marca/logo_claro.png" alt="Hexis Forensics" width="420"></p>

<p align="center"><b>Extraction and preservation of digital evidence — free and open source</b><br>
Android · iPhone · USB drives and disks · guided by the ISO/IEC 27037 standard</p>

<p align="center">
  <a href="https://github.com/HexisForensics/HexisForensics/releases/latest">
    <img src="https://img.shields.io/badge/%E2%AC%87%20Download%20for%20Windows-installer%20%2B%20manual-1f6feb?style=for-the-badge" alt="Download for Windows">
  </a>
</p>

<p align="center">On the download page you will find the <b>installer</b>, its <b>SHA-256 hash</b> and the <b>user manual</b> (PDF).<br>
No GitHub account required.</p>

<p align="center">
  📘 <a href="docs/User_Manual_Hexis_Forensics_EN.pdf">User Manual</a> ·
  ⚡ <a href="docs/Quick_Extraction_Guide_Hexis_Forensics_EN.pdf">Quick Extraction Guide</a> ·
  🧪 <a href="docs/Practice_Guide_Emulator_Hexis_Forensics_EN.pdf">Emulator Practice Guide</a>
</p>

> ℹ️ **The program and the documents it generates (reports and the expert report) are in Portuguese.**
> This English documentation explains how to operate it; the names of the buttons are
> quoted in Portuguese, as they appear in the interface.

---

## What it is

**Hexis Forensics** is a tool for the routine work of device forensics: collect what
answers the examination, record how each piece of data was obtained and deliver
documents that stand on their own.

- **Android** — address book, calls, SMS and MMS, media, WhatsApp (via the backup
  with a 64-digit key), system artifacts, diagnostic report.
- **iPhone** — local backup, common or encrypted (which brings the call log), with
  decryption, messages, address book, WhatsApp and photos.
- **USB drives and disks** — logical copy, Windows artifacts and a volume image,
  with a write blocker.
- **Hash sealing** — the SHA-256 of each file is computed at the moment of
  acquisition, and integrity can be checked at any time.
- **Documents** — Extraction Report, Content Report (with the photo locations),
  PDF of selected conversations and the Expert Report.
- **Examination without extraction** — the report of the locked or damaged device,
  with the same chain of custody.

## The principles

1. **Never assert what was not verified.** When a piece of data is not obtained, the
   document says why. The absence of a piece of data in the material is never
   presented as its absence on the device.
2. **Every change to the device is recorded and justified.** The modules that modify
   the device start unchecked and leave a record of what was done.
3. **What is necessary, well recorded.** Collect what matters to the examination and
   document the provenance of each piece of data.

## How to install

### Option 1 — Installer for Windows (recommended)

1. Download the installer on the [download page](https://github.com/HexisForensics/HexisForensics/releases/latest).
2. **Verify the hash.** In the file's folder, open the Terminal and type
   `Get-FileHash .\HexisForensics-Setup-1.0.0.exe`. The value must be identical to the
   one published on the download page.
3. Run the installer. As it has no paid digital signature, Windows shows
   **"Windows protected your PC"**: click **More info** and then **Run anyway**.
4. On the first run, register your examiner profile and save the password
   **recovery code**.

> On some computers, **Smart App Control** on Windows 11 blocks the installer
> **without** offering the "Run anyway" button, because it has no digital signature.
> In that case, install on another computer, ask your IT department to allow the
> program, or use **Option 2** below.

### Option 2 — Run from source

When the installer is blocked and there is no way to allow it, the tool runs directly
from source, like any open-source project. It takes a few more steps, but it does not
depend on a digital signature.

1. Install **Python 3.13** ([on the downloads page](https://www.python.org/downloads/),
   choose version **3.13** — **not** 3.14, which one of the iPhone libraries does not
   support yet). On the first screen of the Python installer, check
   **Add python.exe to PATH**.
2. Download the **source (ZIP)** of the tagged version, on the
   [releases page](https://github.com/HexisForensics/HexisForensics/releases)
   — **not** the "Code → Download ZIP" from the main page, which brings the development
   version. Verify the ZIP's hash (`Get-FileHash .\HexisForensics-1.0.0-fonte.zip`),
   identical to the one published in the Release, and extract the folder.
3. Open the extracted folder, right-click an empty space and choose
   **Open in Terminal**.
4. Install the libraries and open the tool:

   ```
   py -m pip install -r requirements.txt
   py main.py
   ```

The `adb.exe` already comes in the ZIP, so Android extraction works with no extra step.
Cases are kept in **HexisForensics-Casos**, in your Windows user folder — the same as
the installed version, **outside** the program folder, so that updating (downloading the
new ZIP) never reaches the acquisitions.

The [manual](docs/User_Manual_Hexis_Forensics_EN.pdf) explains each step, with the
screens; the **Quick Extraction Guide** above is also in English.

**Requirements:** Windows 10 or 11 and a USB data cable. For iPhone, the
**Apple Devices** app (Microsoft Store) or iTunes.

## Where version 1.0 was proven

| Device | System |
|---|---|
| Motorola moto x4 | Android 9 |
| Samsung Galaxy A22 | Android 13 (One UI 5.1) |
| Android emulator, with elevated privilege | Android 13 |
| iPhone 11 | iOS 18.6.2 |
| USB drive | Windows 11 |

Other models tend to work by the same route, but were not verified.
**Known limitation:** the agent app has not yet been verified on **Xiaomi, Redmi and
POCO** devices. The full list of limitations is in the manual.

## What the tool does not do

It does not unlock devices, does not bypass passcodes, does not perform physical
extraction of a phone without elevated privilege and does not recover deleted data. For
those cases there are specialized tools.

## For developers

The code is organized in three layers (`core` → `services` → `ui`), with an automated
test suite. To run the suite, see **Option 2** above and run the tool from source. The
technical documentation is in [docs/DESENVOLVIMENTO.md](docs/DESENVOLVIMENTO.md) (in
Portuguese).

```
py tests/rodar_todos.py
```

## Contact

Questions and comments: **contatohexisforensics@gmail.com**

LinkedIn: [Hexis Forensics](https://www.linkedin.com/in/hexis-forensics-75779344a)

## License

Copyright (C) 2026 Hexis Forensics.

Hexis Forensics is free software: it may be redistributed and modified under the terms of
the **GNU General Public License, version 3** (GPL-3.0), published by the Free Software
Foundation. Whoever distributes a modified version must also distribute it under the
GPL-3.0, with the source code.

It is distributed in the hope that it will be useful, but **without any warranty** — not
even the implied warranty of merchantability or fitness for a particular purpose. The
full text is in the [LICENSE](LICENSE) file.

The third-party libraries that accompany the installer keep their own licenses:
pymobiledevice3 and pyiosbackup (GPL-3.0), PySide6 (LGPL-3.0), reportlab (BSD),
cryptography and packaging (Apache-2.0/BSD) and Android's ADB (Apache-2.0).
