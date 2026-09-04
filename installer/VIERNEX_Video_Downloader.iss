#define MyAppName "VIER-NEX Video Downloader"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Bryant Brugal"
#define MyAppExeName "VIER-NEX Video Downloader.exe"

[Setup]
SourceDir=..
AppId={{B8D6B407-8A5D-49F3-A466-52C19BA049B1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\VIER-NEX Video Downloader
DefaultGroupName=VIER-NEX Video Downloader
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=release
OutputBaseFilename=VIER-NEX-Video-Downloader-Setup-v{#MyAppVersion}
SetupIconFile=VIERNEX_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "VIER-NEX_Manual_de_Usuario.pdf"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\VIER-NEX Video Downloader"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\VIER-NEX Video Downloader"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir VIER-NEX Video Downloader"; Flags: nowait postinstall skipifsilent

