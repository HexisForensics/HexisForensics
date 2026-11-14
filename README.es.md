🌐 **Español** · [Português](README.md) · [English](README.en.md)

<p align="center"><img src="assets/marca/logo_claro.png" alt="Hexis Forensics" width="420"></p>

<p align="center"><b>Extracción y preservación de evidencia digital — gratuita y de código abierto</b><br>
Android · iPhone · memorias USB y discos · orientada por la norma ISO/IEC 27037</p>

<p align="center">
  <a href="https://github.com/HexisForensics/HexisForensics/releases/latest">
    <img src="https://img.shields.io/badge/%E2%AC%87%20Descargar%20para%20Windows-instalador%20%2B%20manual-1f6feb?style=for-the-badge" alt="Descargar para Windows">
  </a>
</p>

<p align="center">En la página de descarga están el <b>instalador</b>, su <b>hash SHA-256</b> y el <b>manual del usuario</b> (PDF).<br>
No hace falta cuenta en GitHub.</p>

<p align="center">
  📘 <a href="docs/Manual_Usuario_Hexis_Forensics_ES.pdf">Manual del Usuario</a> ·
  ⚡ <a href="docs/Guia_Extraccion_Rapida_Hexis_Forensics_ES.pdf">Guía de Extracción Rápida</a>
</p>

> ℹ️ **El programa y los documentos que genera (informes y laudo) están en portugués.**
> Esta documentación en español explica cómo operarlo; los nombres de los botones
> se citan en portugués, como aparecen en la interfaz.

---

## Qué es

El **Hexis Forensics** es una herramienta para el procedimiento de rutina de la
pericia en dispositivos: recolectar lo que responde al examen, registrar cómo se
obtuvo cada dato y entregar documentos que se sostienen por sí solos.

- **Android** — agenda, llamadas, SMS y MMS, medios, WhatsApp (por la copia de
  seguridad con clave de 64 dígitos), artefactos del sistema, informe de diagnóstico.
- **iPhone** — copia de seguridad local común o cifrada (que trae el registro de
  llamadas), con descifrado, mensajes, agenda, WhatsApp y fotos.
- **Memorias USB y discos** — copia lógica, artefactos de Windows e imagen del
  volumen, con bloqueador de escritura.
- **Sellado por hash** — el SHA-256 de cada archivo se calcula en el momento de la
  adquisición, y la integridad puede verificarse en cualquier momento.
- **Documentos** — Informe de Extracción, Informe de Contenido (con las
  ubicaciones de las fotos), PDF de conversaciones seleccionadas e Informe Pericial.
- **Examen sin extracción** — el informe del dispositivo bloqueado o dañado, con la
  misma cadena de custodia.

## Los principios

1. **Nunca afirmar lo que no se verificó.** Cuando un dato no se obtiene, el
   documento dice por qué. La ausencia de un dato en el material nunca se presenta
   como ausencia del dato en el dispositivo.
2. **Toda alteración en el dispositivo se registra y se justifica.** Los módulos que
   modifican el dispositivo comienzan sin marcar y dejan el registro de lo que se hizo.
3. **Lo necesario, bien registrado.** Recolectar lo que interesa al examen y
   documentar la procedencia de cada dato.

## Cómo instalar

### Opción 1 — Instalador para Windows (recomendado)

1. Descargue el instalador en la [página de descarga](https://github.com/HexisForensics/HexisForensics/releases/latest).
2. **Verifique el hash.** En la carpeta del archivo, abra la Terminal y escriba
   `Get-FileHash .\HexisForensics-Setup-1.0.0.exe`. El valor debe ser idéntico al
   publicado en la página de descarga.
3. Ejecute el instalador. Como no tiene firma digital pagada, Windows muestra
   **«Windows protegió su PC»**: haga clic en **Más información** y en
   **Ejecutar de todas formas**.
4. En el primer inicio, registre su perfil de examinador y guarde el
   **código de recuperación** de la contraseña.

> En algunas computadoras el **Control Inteligente de Aplicaciones** de Windows 11
> bloquea el instalador **sin** ofrecer el botón «Ejecutar de todas formas», por no
> tener firma digital. En ese caso, instale en otra computadora, pida al área de TI
> que autorice el programa, o use la **Opción 2** de abajo.

### Opción 2 — Ejecutar desde el código fuente

Cuando el instalador se bloquea y no hay forma de autorizarlo, la herramienta se
ejecuta directamente desde el código fuente, como cualquier proyecto de código
abierto. Exige algunos pasos más, pero no depende de firma digital.

1. Instale **Python 3.13** ([en la página de descargas](https://www.python.org/downloads/),
   elija la versión **3.13** — **no** la 3.14, que aún no tiene una de las bibliotecas
   del iPhone). En la primera pantalla del instalador de Python, marque
   **Add python.exe to PATH**.
2. Descargue el **Fuente (ZIP)** de la versión etiquetada, en la
   [página de versiones](https://github.com/HexisForensics/HexisForensics/releases)
   — **no** el «Code → Download ZIP» de la página principal, que trae la versión en
   desarrollo. Verifique el hash del ZIP (`Get-FileHash .\HexisForensics-1.0.0-fonte.zip`),
   idéntico al publicado en la Release, y extraiga la carpeta.
3. Abra la carpeta extraída, haga clic derecho en un espacio vacío y elija
   **Abrir en la Terminal**.
4. Instale las bibliotecas y abra la herramienta:

   ```
   py -m pip install -r requirements.txt
   py main.py
   ```

El `adb.exe` ya viene en el ZIP, así que la extracción de Android funciona sin paso
extra. Los casos quedan en **HexisForensics-Casos**, en su carpeta de usuario de
Windows — la misma de la versión instalada, **fuera** de la carpeta del programa,
para que actualizar (descargar el ZIP nuevo) nunca alcance las adquisiciones.

El [manual](docs/Manual_Usuario_Hexis_Forensics_ES.pdf) explica cada paso, con las
pantallas; la **Guía de Extracción Rápida** de arriba también está en español.

**Requisitos:** Windows 10 u 11 y cable USB de datos. Para iPhone, la aplicación
**Dispositivos Apple** (Microsoft Store) o iTunes.

## Dónde se probó la versión 1.0

| Dispositivo | Sistema |
|---|---|
| Motorola moto x4 | Android 9 |
| Samsung Galaxy A22 | Android 13 (One UI 5.1) |
| Emulador Android, con privilegios elevados | Android 13 |
| iPhone 11 | iOS 18.6.2 |
| Memoria USB | Windows 11 |

Otros modelos tienden a funcionar por el mismo camino, pero no fueron verificados.
**Limitación conocida:** la aplicación agente aún no fue verificada en dispositivos
**Xiaomi, Redmi y POCO**. La lista completa de limitaciones está en el manual.

## Lo que la herramienta no hace

No desbloquea dispositivos, no sortea contraseñas, no hace extracción física de
celular sin privilegios elevados y no recupera datos borrados. Para esos casos
existen herramientas especializadas.

## Para quien programa

El código está organizado en tres capas (`core` → `services` → `ui`), con una suite
de pruebas automatizadas. Para ejecutar la suite, vea la **Opción 2** de arriba y
ejecute la herramienta desde el código fuente. La documentación técnica está en
[docs/DESENVOLVIMENTO.md](docs/DESENVOLVIMENTO.md) (en portugués).

```
py tests/rodar_todos.py
```

## Contacto

Dudas y comentarios: **contatohexisforensics@gmail.com**

LinkedIn: [Hexis Forensics](https://www.linkedin.com/in/hexis-forensics-75779344a)

## Licencia

Copyright (C) 2026 Hexis Forensics.

El Hexis Forensics es software libre: puede redistribuirse y modificarse bajo los
términos de la **GNU General Public License, versión 3** (GPL-3.0), publicada por la
Free Software Foundation. Quien distribuya una versión modificada debe distribuirla
también bajo la GPL-3.0, con el código fuente.

Se distribuye con la expectativa de ser útil, pero **sin ninguna garantía** — ni
siquiera la implícita de comerciabilidad o de adecuación a un propósito específico.
El texto íntegro está en el archivo [LICENSE](LICENSE).

Las bibliotecas de terceros que acompañan al instalador mantienen sus propias
licencias: pymobiledevice3 y pyiosbackup (GPL-3.0), PySide6 (LGPL-3.0), reportlab
(BSD), cryptography y packaging (Apache-2.0/BSD) y el ADB de Android (Apache-2.0).
