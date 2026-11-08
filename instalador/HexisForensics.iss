; Instalador do Hexis Forensics (Inno Setup 6).
;
; Gerado por:  py empacotar.py --instalador
; que monta antes a pasta portatil (dist\HexisForensics-portatil) e a
; verifica executando a suite de testes com o interpretador que vai dentro.
;
; O que este instalador entrega e a pasta PORTATIL: o interpretador Python
; assinado pelo fabricante ao lado do codigo da suite, legivel. Nada e
; compilado num executavel proprio -- o que roda pode ser lido e conferido
; contra HASHES_DO_CODIGO.sha256.
;
; Instala por usuario, sem pedir Administrador. Os CASOS nao ficam na pasta
; do programa: vao para %USERPROFILE%\HexisForensics-Casos (ver
; core/instalacao.py), e a desinstalacao nao toca neles.

#ifndef Versao
  #define Versao "0.0.0"
#endif

#define Nome "Hexis Forensics"
#define Portatil "..\dist\HexisForensics-portatil"

[Setup]
AppId={{6F1B0E7C-3D2A-4C55-9E0B-F04E7A1C2D31}
AppName={#Nome}
AppVersion={#Versao}
AppVerName={#Nome} {#Versao}
AppPublisher=Hexis Forensics
DefaultDirName={localappdata}\Programs\HexisForensics
DefaultGroupName={#Nome}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=HexisForensics-Setup-{#Versao}
SetupIconFile=..\assets\marca\icone.ico
UninstallDisplayIcon={app}\assets\marca\icone.ico
UninstallDisplayName={#Nome} {#Versao}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Termos de uso: o aceite e obrigatorio (texto gerado de core/termos.py).
LicenseFile=TERMOS_DE_USO.txt
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalhodesktop"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Dirs]
Name: "{%USERPROFILE}\HexisForensics-Casos"

[Files]
; As extracoes de quem empacotou nunca viajam no instalador, e APK posto em
; binario\ (o do metodo de substituicao do WhatsApp) tambem nao: cada
; examinador fornece o seu.
Source: "{#Portatil}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "\extracoes\*,\binario\*.apk,__pycache__,*.pyc"
Source: "instalada.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#Nome}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-s -E -B ""{app}\main.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\marca\icone.ico"; Comment: "Aquisição e preservação de evidência digital"
Name: "{group}\{#Nome} (como Administrador)"; Filename: "{app}\Abrir como Administrador.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\marca\icone.ico"; Comment: "Necessário para a Imagem do Volume"
Name: "{group}\Pasta de casos"; Filename: "{%USERPROFILE}\HexisForensics-Casos"
Name: "{group}\Desinstalar {#Nome}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#Nome}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-s -E -B ""{app}\main.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\marca\icone.ico"; Tasks: atalhodesktop

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-s -E -B ""{app}\main.py"""; WorkingDir: "{app}"; Description: "Abrir o {#Nome}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Só o que a própria suíte gera ao rodar. Os casos ficam fora de {app}.
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\core\__pycache__"
Type: filesandordirs; Name: "{app}\services\__pycache__"
Type: filesandordirs; Name: "{app}\ui\__pycache__"
