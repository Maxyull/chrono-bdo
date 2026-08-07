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
; ⛔ **`no`, et ce n'est pas un renoncement, c'est le contraire.**
; Il valait `yes`, et la relance reposait donc entièrement sur le
; Gestionnaire de redémarrage de Windows. Constaté par Maxime en cliquant
; pour de vrai le 07/08/2026 : Rubin ne revenait pas. Butin, le logiciel
; jumeau, a rencontré le MÊME défaut le MÊME jour et l'a tranché ainsi ;
; Rubin s'aligne sur lui plutôt que d'entretenir deux mécanismes.
;
; La relance est désormais une ligne explicite de la section [Run],
; conditionnée à `/RELANCER`. Un mécanisme qu'on peut lire, tester et voir
; échouer, au lieu d'un comportement du système qu'on espère.
;
; ⚠️ **Les deux ne doivent JAMAIS être actifs ensemble** : le Gestionnaire
; de redémarrage et la section [Run] rouvriraient chacun leur exemplaire,
; et deux Rubin en parallèle voudraient dire deux fils de capture sur la
; même session, donc deux fois la même quête envoyée au serveur.
RestartApplications=no
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
; Installation manuelle : la case « Lancer Rubin » de la dernière page.
; `skipifsilent` la retire en mode silencieux, ce qui est correct ICI, mais
; c'était la SEULE chose qui rouvrait Rubin, et la mise à jour en un clic
; passe justement en `/VERYSILENT`. Voir la ligne suivante.
Filename: "{app}\rubin.exe"; Description: "Lancer Rubin"; Flags: nowait postinstall skipifsilent

; ⛔ La relance après une mise à jour en un clic, EXPLICITE.
;
; ⚠️ `/RELANCER` et non « toujours en silencieux » : une construction pourrait
; un jour installer en silencieux pour vérifier le paquet, et elle n'aurait
; aucune raison d'ouvrir une fenêtre au milieu. Seule la mise à jour le demande.
Filename: "{app}\rubin.exe"; Flags: nowait; Check: RelancementDemande

[Code]
{ ⚠️ Inno Setup n'a PAS de `CmdLineParamExists`. La session butin-bdo s'y est
  cassé les dents le 07/08/2026, ISCC refusant net « Unknown identifier » : le
  parcours de `ParamStr` est l'idiome, et il faut l'écrire soi-même. Repris de
  `butin-bdo/installeur/butin.iss` pour que les deux logiciels se relancent de
  la même façon.

  `CompareText` ignore la casse, donc `/relancer` marche aussi. }
function ParametrePresent(const Valeur: string): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Valeur) = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

function RelancementDemande(): Boolean;
begin
  Result := ParametrePresent('/RELANCER');
end;
