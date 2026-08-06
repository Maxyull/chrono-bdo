; Installateur Windows de Rubin, avec Inno Setup.
;
; Compilé par construire.py, jamais à la main :
;   ISCC.exe /DVersion=0.5.5 empaquetage\rubin.iss
;
; Ce que ce fichier apporte par rapport au zip seul (empaquetage/construire.py) :
; un raccourci menu Démarrer, un désinstalleur propre, et surtout la capacité
; d'être relancé en silence pour une mise à jour (voir autoupdate.py) sans
; qu'aucune fenêtre n'apparaisse ni qu'aucun droit administrateur ne soit
; demandé.
;
; ⚠️ PrivilegesRequired=lowest est le choix qui rend la mise à jour automatique
; possible sans UAC. Une installation Program Files exigerait une élévation à
; CHAQUE mise à jour silencieuse, ce qui romprait le "un clic" demandé par
; Maxime le 06/08/2026 : l'utilisateur verrait une invite Windows au moment où
; il s'attend à ce que rien ne se passe.
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
; Fixe, généré une seule fois : c'est lui qui permet à une installation plus
; récente de reconnaître et remplacer la précédente au lieu d'en poser une
; seconde à côté.
AppId={{2EBC0F12-807F-4278-97C3-93BC08975397}
AppName=Rubin
AppVersion={#Version}
AppPublisher=Maxime Lacoste
AppPublisherURL=https://github.com/Maxyull/rubin-bdo
DefaultDirName={localappdata}\Programs\Rubin
DefaultGroupName=Rubin
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=rubin-installateur-{#Version}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Ferme rubin.exe s'il tourne, sans demander : c'est le cœur de la mise à
; jour silencieuse. Utilise le Gestionnaire de redémarrage de Windows, pas
; besoin d'AppMutex côté application.
CloseApplications=force
RestartApplications=yes
UninstallDisplayIcon={app}\rubin.exe
; L'icône de l'installateur lui-même, celle que le testeur voit dans ses
; téléchargements avant d'avoir rien installé. Sans elle, Inno Setup pose la
; sienne, la même pour tous les programmes du monde compilés avec lui.
SetupIconFile=..\src\rubin\interface\data\rubin.ico

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; Flags: unchecked

[Files]
; Le dossier entier produit par PyInstaller, tel quel.
Source: "..\dist\rubin\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Rubin"; Filename: "{app}\rubin.exe"
Name: "{group}\Désinstaller Rubin"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Rubin"; Filename: "{app}\rubin.exe"; Tasks: desktopicon

[Run]
; Coché par défaut : après une installation manuelle, ouvrir Rubin est le
; geste attendu. `/RESTARTAPPLICATIONS`, lui, gère la relance après une mise
; à jour silencieuse : les deux ne se recouvrent pas, une mise à jour
; silencieuse ne passe jamais par cette section.
Filename: "{app}\rubin.exe"; Description: "Lancer Rubin"; Flags: nowait postinstall skipifsilent
