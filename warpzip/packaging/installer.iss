; Inno Setup 6 script.  Build:  iscc packaging\installer.iss  (after PyInstaller)
#define AppName      "WARPZIP"
#define AppNameKo    "워프집"
#define AppVersion   GetEnv("WARPZIP_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0.0"
#endif
#define AppPublisher "WarpZip"
#define AppExe       "WarpZip.exe"

[Setup]
AppId={{6D1C6E0A-4F0B-4B7B-9C55-7A4E7B5A31D2}
AppName={#AppName} {#AppNameKo}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\WarpZip
DefaultGroupName=WARPZIP
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\dist
OutputBaseFilename=WarpZip-{#AppVersion}-setup
SetupIconFile=..\src\warpzip\assets\app.ico
WizardImageFile=wizard.bmp
WizardSmallImageFile=wizard_small.bmp
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
; LicenseFile=..\EULA.txt   <- add your end-user licence agreement before shipping

[Languages]
#if FileExists(CompilerPath + "Languages\Korean.isl")
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.TaskContext=Add "Compress / Extract with WARPZIP" to the Explorer right-click menu
korean.TaskContext=탐색기 우클릭 메뉴에 "WARPZIP으로 압축/풀기" 추가
english.TaskAssoc=Register WARPZIP for archive file types (zip, 7z, rar, tar, gz...)
korean.TaskAssoc=압축 파일 형식(zip, 7z, rar, tar, gz…)에 WARPZIP 등록
english.LaunchApp=Launch WARPZIP
korean.LaunchApp=워프집 실행하기

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked
Name: "context"; Description: "{cm:TaskContext}"
Name: "assoc"; Description: "{cm:TaskAssoc}"

[Files]
Source: "..\dist\WarpZip\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\WARPZIP"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\WARPZIP"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--install-shell {code:Lang}"; Tasks: context; Flags: runhidden
Filename: "{app}\{#AppExe}"; Parameters: "--register-assoc {code:Lang}"; Tasks: assoc; Flags: runhidden
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#AppExe}"; Parameters: "--uninstall-shell"; Flags: runhidden; RunOnceId: "WarpZipShell"

[Code]
function Lang(Param: String): String;
begin
  if ActiveLanguage = 'korean' then Result := 'ko' else Result := 'en';
end;
