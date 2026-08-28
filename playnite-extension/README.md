# Extension Playnite — Export des succès

Déclenche l'extraction des succès à la fermeture d'un jeu, et fournit à
l'extracteur les temps de jeu connus de Playnite.

## Pourquoi passer par une extension

La bibliothèque de Playnite (`games.db`) est une base LiteDB, verrouillée tant
que Playnite tourne et sans lecteur Python fiable. Les temps de jeu ne sont donc
pas lisibles depuis l'extracteur : c'est l'extension, qui a accès à l'API
Playnite, qui les exporte dans un JSON simple.

Intérêt par rapport à Steam : Playnite compte aussi les parties lancées **hors**
Steam, là où le `Playtime` de Steam ne voit que ce qui passe par son client.

## Enchaînement

```
[Playnite] fermeture d'un jeu
   └─ OnGameStopped
        ├─ écrit playnite_playtime.json  (appid Steam → minutes jouées)
        └─ lance  python -m extractor --output-dir <partage> --playnite <ce fichier>
                     └─ le temps Playnite prime sur celui de Steam
```

## Compiler

Nécessite le SDK .NET (testé avec 8.0). Ni Visual Studio ni targeting pack
.NET Framework ne sont requis : le paquet `Microsoft.NETFramework.ReferenceAssemblies`
permet de cibler net462, la plateforme de Playnite 10.

```bash
dotnet build -c Release
```

Le projet référence `Playnite.SDK.dll` depuis `%LOCALAPPDATA%\Playnite`. Pour une
installation ailleurs :

```bash
dotnet build -c Release -p:PlayniteSdkPath="D:\Playnite\Playnite.SDK.dll"
```

## Installer

Copier `AchievementsExporter.dll` et `extension.yaml` dans
`%APPDATA%\Playnite\Extensions\AchievementsExporter\`, puis **redémarrer
Playnite** (les extensions ne sont chargées qu'au démarrage).

```powershell
$dest = "$env:APPDATA\Playnite\Extensions\AchievementsExporter"
New-Item -ItemType Directory -Force -Path $dest
Copy-Item bin\Release\AchievementsExporter.dll, extension.yaml $dest -Force
```

## Régler

Dans Playnite : **Paramètres → Extensions → Export des succès**.

| Réglage | Exemple |
|---|---|
| Chemin de `python.exe` | `S:\Achievements\.venv\Scripts\python.exe` |
| Dossier du projet | `S:\Achievements` |
| Dossier partagé de destination | `\\192.168.1.98\smbShared\achievements` |
| Fichier des temps de jeu | *(vide = dossier de données du plugin)* |

Tant que le chemin Python ou le dossier de destination ne sont pas renseignés,
l'extension écrit quand même les temps de jeu mais ne lance pas l'extracteur —
et le signale dans le journal de Playnite.

## Correspondance des jeux

L'outil est indexé par **appid Steam**, puisque les succès viennent du cache
Steam local. L'extension classe donc chaque jeu Playnite en deux catégories :

- **`games`** — jeux importés par le plugin Steam de Playnite : leur `GameId`
  *est* l'appid, la correspondance est directe. C'est le cas de Cyberpunk 2077
  et Elden Ring, dont le temps réel remplace alors le temps Steam.
- **`unmatched`** — jeux ajoutés à la main ou venant d'un autre launcher. Sans
  appid Steam, ils ne peuvent pas être reliés à des succès. Ils sont tout de
  même listés dans le JSON, à titre de diagnostic.

À noter : un jeu absent du cache de succès Steam (jamais lancé via Steam)
n'apparaît de toute façon pas dans le tableau de bord, temps de jeu ou non.

## Dépannage

Le journal de Playnite (`%APPDATA%\Playnite\playnite.log`) contient les lignes
de l'extension : nombre de jeux exportés, commande lancée, et toute erreur.
En cas d'échec, une notification Playnite est affichée si l'option est cochée.
