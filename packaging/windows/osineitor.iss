; Instalador de OSINEITOR para Windows (Inno Setup 6).
; Compilar: ISCC /DMyAppVersion=0.5.0 packaging\windows\osineitor.iss  (tras build.ps1).
; La versión viene siempre de la compilación: no se fija aquí.
#ifndef MyAppVersion
  #error Pasa la versión con /DMyAppVersion=x.y.z
#endif

[Setup]
; GUID fijo: identifica la aplicación para actualizar y desinstalar. No lo cambies nunca.
AppId={{5B0F7C1E-3A92-4D8B-9E64-0C2A71D5F3B8}
AppName=OSINEITOR
AppVersion={#MyAppVersion}
AppPublisher=OSINEITOR
DefaultDirName={autopf}\OSINEITOR
DefaultGroupName=OSINEITOR
DisableProgramGroupPage=yes
; Por usuario: sin elevación (UAC) y sin tocar Archivos de programa.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
OutputDir=..\..\dist
OutputBaseFilename=OSINEITOR-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\osineitor-gui.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "addtopath"; Description: "Añadir la CLI «osineitor» al PATH del usuario"; Flags: unchecked

[Files]
Source: "..\..\dist\OSINEITOR\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\OSINEITOR"; Filename: "{app}\osineitor-gui.exe"

[Registry]
; Solo el PATH del usuario (HKCU): nunca el del sistema.
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\osineitor-gui.exe"; Description: "Abrir OSINEITOR"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsAddPath(Param: string): Boolean;
var
  Current: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Current) then
    Current := '';
  Result := Pos(';' + Lowercase(Param) + ';', ';' + Lowercase(Current) + ';') = 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Current, Entry, Padded: string;
  P: Integer;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Current) then
    Exit;
  Entry := ExpandConstant('{app}');
  // La entrada entera, entre `;`: buscar solo el prefijo recortaría también `...\OSINEITOR2`.
  Padded := ';' + Current + ';';
  P := Pos(';' + Lowercase(Entry) + ';', Lowercase(Padded));
  if P = 0 then
    Exit;
  Delete(Padded, P, Length(Entry) + 1);
  Current := Copy(Padded, 2, Length(Padded) - 2);
  RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Current);
end;
