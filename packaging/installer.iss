; Installer for Smart Building Translator (Inno Setup 6). Built by packaging/build.py:
;   ISCC.exe /DAppVersion=1.0.0 /O<dist> packaging\installer.iss
;
; Per-user installation (no administrator rights): %LOCALAPPDATA%\Programs\Smart Building Translator.
; Nothing is downloaded by the installer. Glossaries, history and models live in %LOCALAPPDATA%\SmartBuildingTranslator;
; uninstalling asks before deleting them.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Smart Building Translator"
#define AppExe "SmartBuildingTranslator.exe"

[Setup]
AppId={{6E0F3C2B-8A4D-4F7E-9B1C-5D2A7E8F9C30}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=kyawsithu-cloud
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=SmartBuildingTranslator-{#AppVersion}-Setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; an update replaces the program files completely (no leftovers from the previous version)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\SmartBuildingTranslator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2Key = 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2Installed: Boolean;
var
  Version: String;
begin
  Result := (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\' + WebView2Key, 'pv', Version) or
             RegQueryStringValue(HKLM, 'SOFTWARE\' + WebView2Key, 'pv', Version) or
             RegQueryStringValue(HKCU, 'Software\' + WebView2Key, 'pv', Version))
            and (Version <> '') and (Version <> '0.0.0.0');
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if not WebView2Installed then
    Result := MsgBox('The Microsoft Edge WebView2 Runtime was not found. Windows 11 includes it; on other systems ' +
                     'install it from Microsoft (search for "WebView2 Runtime"), then start the app.' + #13#10#13#10 +
                     'Continue the installation anyway?', mbConfirmation, MB_YESNO) = IDYES;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\SmartBuildingTranslator');
    if DirExists(DataDir) and not UninstallSilent then
      if MsgBox('Also delete your glossaries, translation memory, job history and the downloaded models?' + #13#10 +
                DataDir + #13#10#13#10 + 'Choose No to keep them for a later installation.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
