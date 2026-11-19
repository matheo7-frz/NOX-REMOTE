; Installeur NOX REMOTE - fait par math_0235
Unicode true
!include "MUI2.nsh"

!define APPNAME "NOX REMOTE"
!define EXENAME "NOX-REMOTE.exe"
!define REGKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\NOX-REMOTE"

Name "${APPNAME}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\NOX REMOTE"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Icon "${ROOT}\gui\chiaking.ico"
UninstallIcon "${ROOT}\gui\chiaking.ico"
BrandingText "NOX REMOTE - fait par math_0235"

!define MUI_ICON "${ROOT}\gui\chiaking.ico"
!define MUI_UNICON "${ROOT}\gui\chiaking.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXENAME}"
!define MUI_FINISHPAGE_RUN_TEXT "Lancer NOX REMOTE"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "French"

Section "Installer"
  ; ferme NOX REMOTE s'il tourne (mise à jour)
  nsExec::Exec 'taskkill /F /IM ${EXENAME}'
  SetOutPath "$INSTDIR"
  File /r "${APPDIR}\*.*"
  WriteUninstaller "$INSTDIR\Desinstaller.exe"
  CreateDirectory "$SMPROGRAMS\NOX REMOTE"
  CreateShortcut "$SMPROGRAMS\NOX REMOTE\NOX REMOTE.lnk" "$INSTDIR\${EXENAME}"
  CreateShortcut "$DESKTOP\NOX REMOTE.lnk" "$INSTDIR\${EXENAME}"
  WriteRegStr HKCU "${REGKEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "${REGKEY}" "Publisher" "math_0235"
  WriteRegStr HKCU "${REGKEY}" "DisplayIcon" "$INSTDIR\${EXENAME}"
  WriteRegStr HKCU "${REGKEY}" "UninstallString" '"$INSTDIR\Desinstaller.exe"'
  WriteRegDWORD HKCU "${REGKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${REGKEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /F /IM ${EXENAME}'
  Delete "$DESKTOP\NOX REMOTE.lnk"
  RMDir /r "$SMPROGRAMS\NOX REMOTE"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${REGKEY}"
SectionEnd
