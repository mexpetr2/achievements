# Outil de suivi et visualisation de succès de jeux — Design v1

**Date :** 2026-08-24
**Statut :** Approuvé pour planification

## Contexte

Le dossier `S:\Achievements` contient déjà des analyses manuelles ponctuelles de sauvegardes (Elden Ring, Cyberpunk 2077) réalisées avec SAM (Steam Achievement Manager) pour débloquer des succès non détectés automatiquement par Steam. Ce travail a produit un rapport Markdown (`Cyberpunk 2077/Rapport_Succes_A_Debloquer.md`) mais reste manuel, ponctuel, et confiné à Steam.

L'objectif de ce projet est de construire un outil qui :
- extrait automatiquement l'état réel de vos succès depuis les données **locales** de Steam (pas d'appel réseau/API Steam) ;
- sauvegarde ces données dans le temps ;
- les visualise dans un tableau de bord web, hébergé sur votre NAS avec votre propre nom de domaine, indépendamment de l'interface Steam.

## Objectifs (v1)

- Lire l'état des succès de **tous les jeux Steam installés** ayant des succès, directement depuis les fichiers locaux du client Steam.
- Générer un export JSON lisible par un humain.
- Ingérer ces exports dans une base de données pour les afficher dans un tableau de bord web.
- Héberger ce tableau de bord en conteneur Docker sur le NAS, accessible via un nom de domaine personnel, protégé par mot de passe.
- Transfert des données PC → NAS via un dossier réseau partagé surveillé (pas d'upload manuel, pas d'API).

## Hors scope (v1)

- **Succès déduits/non officiels avec niveau de confiance** (comme le rapport Cyberpunk existant) — l'outil reflète fidèlement uniquement ce que Steam a réellement débloqué en local. Pourra être ajouté plus tard si besoin.
- **Intégration Playnite** (déclenchement automatique de l'export à la fermeture d'un jeu, à la manière de l'extension communautaire Ludusavi/Playnite qui hook `OnGameStopped`) — prévu pour une **v2**. En v1, l'extracteur est lancé manuellement ou via une tâche planifiée Windows.
- Jeux non-Steam (GOG, Epic...) — pourra être envisagé plus tard, potentiellement en lien avec l'intégration Playnite en v2, qui centralise déjà plusieurs launchers.
- Jeux Steam **possédés mais non installés** — sans API en ligne, seule la liste des jeux installés (fichiers `.acf`) est détectable localement. Un jeu désinstallé après avoir été platiné resterait donc absent tant qu'il n'est pas réinstallé au moins une fois pour régénérer son cache local.
- Historique/timeline de progression dans le temps au-delà de la date de déblocage native fournie par Steam — pas de graphe de tendance en v1.
- Tests end-to-end automatisés du conteneur Docker complet.

## Architecture

```
[PC Windows]                    [Dossier partagé NAS]         [NAS Docker]
Steam (cache local)
     │
     ▼
extractor.py  ──────►  succes_<horodatage>.json  ──────►  appli web (poll + ingère)
(lit les .bin Steam)         (JSON lisible)              (SQLite + tableau de bord)
                                                                      │
                                                                      ▼
                                                          https://votredomaine.tld
                                                          (protégé par mot de passe)
```

Deux composants indépendants reliés uniquement par des fichiers JSON dans un dossier partagé. Aucun appel réseau vers Steam à aucun moment (hors affichage d'icônes, voir plus bas).

Stack technique : **Python partout** (cohérent avec la configuration Python déjà présente dans ce dossier — `.ruff_cache`).

## Composants

### 1. Extracteur (`extractor.py`, PC Windows)

Script Python lancé manuellement ou via le Planificateur de tâches Windows.

Étapes :
1. Localise l'installation Steam (registre Windows ou chemins par défaut) et le compte actif via `loginusers.vdf`.
2. Énumère les jeux avec succès à partir des fichiers `appmanifest_<appid>.acf` des jeux **installés** (limite v1 documentée ci-dessus).
3. Pour chaque jeu :
   - lit `UserGameStatsSchema_<appid>.bin` (définitions : nom, description, icône) — format VDF binaire ;
   - lit `UserGameStats_<steamid>_<appid>.bin` (état débloqué + date de déblocage) — format VDF binaire.
4. Écrit `succes_<horodatage>.json` dans le dossier partagé (un objet par jeu, avec la liste de ses succès).

Format de sortie (exemple synthétique) :
```json
{
  "exported_at": "2026-08-24T22:10:00",
  "steam_id": "76561198000000000",
  "games": [
    {
      "appid": 1245620,
      "name": "Elden Ring",
      "achievements": [
        {
          "api_name": "ACH_001",
          "name": "Renard chasseur",
          "description": "Description exemple",
          "icon": "https://example.invalid/icon.jpg",
          "unlocked": true,
          "unlock_time": "2024-03-12T18:44:00"
        }
      ]
    }
  ]
}
```

### 2. Appli web (Docker, NAS)

Une seule image Docker : Flask + SQLite embarqué + tâche de fond, pas de service séparé.

- **Tâche de fond** : sonde le dossier partagé toutes les 5 minutes (valeur par défaut, configurable), ingère les nouveaux fichiers JSON dans SQLite (upsert par jeu/succès), déplace le fichier traité dans un sous-dossier `importés/` (ou `erreurs/` en cas de fichier invalide).
- **Pages** :
  - Accueil : liste des jeux avec % de complétion, flux des derniers succès débloqués tous jeux confondus.
  - Détail par jeu : grille des succès (verrouillé/déverrouillé, icône, description, date de déblocage).
- **Authentification** : mot de passe unique, session cookie, avant tout accès au tableau de bord.

### Modèle de données (SQLite)

- `games` (appid, name, ...)
- `achievements` (appid, api_name, name, description, icon, unlocked, unlock_time)
- `imports` (journal des fichiers ingérés — nom de fichier, date de traitement, statut — pour diagnostic uniquement ; pas d'historique de progression complexe, la date de déblocage faisant déjà foi via Steam)

### Icônes

L'extracteur tente de résoudre les icônes depuis le cache Steam local ; si indisponible, stocke l'URL Steam CDN telle quelle. L'appli web les affiche en `<img src="...">` — la requête réseau, si elle a lieu, part du navigateur qui consulte le site, jamais du NAS ni du PC. **Point technique à valider pendant l'implémentation**, pas une décision bloquante du design.

## Gestion des erreurs

- Fichier Steam introuvable/illisible pour un jeu donné (jamais lancé, format inattendu) → l'extracteur saute ce jeu, log un avertissement, continue les autres.
- JSON malformé ou incomplet arrivant dans le dossier partagé → l'appli l'ignore et le déplace dans `erreurs/` plutôt que de planter l'ingestion.
- Dossier partagé injoignable (NAS éteint, partage réseau coupé) → l'extracteur écrit un message clair et s'arrête proprement ; aucune perte, il suffit de relancer plus tard.

## Tests

- Extracteur : tests unitaires du parseur VDF binaire avec des fixtures d'exemple, sans dépendre d'une vraie installation Steam.
- Appli web : tests de l'ingestion (JSON → SQLite) et des routes principales (authentification, accueil, détail jeu).
- Pas de test end-to-end automatisé du conteneur Docker complet en v1 — vérification manuelle après déploiement.

## Évolutions futures (hors v1, notées pour mémoire)

- Extension Playnite (PowerShell ou C#/.NET, décision reportée) déclenchant l'extraction à la fermeture d'un jeu, sur le modèle de l'intégration Ludusavi/Playnite (`OnGameStopped`).
- Support d'autres launchers via Playnite (GOG, Epic...).
- Réintégration éventuelle des succès déduits/non officiels avec niveau de confiance (comme le rapport Cyberpunk existant), en plus des succès Steam réels.
