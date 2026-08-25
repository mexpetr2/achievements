# Suivi de succès de jeux

Extrait l'état réel de vos succès depuis les **fichiers locaux de Steam**, et les
affiche dans un tableau de bord web hébergé sur votre NAS. Aucune requête vers
l'API Steam : tout est lu sur disque.

## Architecture

```
[PC Windows]                [Dossier partagé NAS]      [NAS Docker]
Steam (appcache/stats)
     │
     ▼
python -m extractor  ──►  succes_<horodatage>.json  ──►  appli web (surveille + ingère)
                                                                 │
                                                                 ▼
                                                    https://votredomaine.tld
```

## 1. Extracteur (PC Windows)

Installation :

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Lancement (remplacer le chemin par votre dossier partagé) :

```bash
.venv/Scripts/python.exe -m extractor --output-dir "\\NAS\partage\succes"
```

Options : `--stats-dir` et `--account-id` remplacent la détection automatique,
`--verbose` affiche les jeux ignorés.

### Automatiser (Planificateur de tâches Windows)

Créer une tâche déclenchée à l'ouverture de session :
- Programme : `S:\Achievements\.venv\Scripts\python.exe`
- Arguments : `-m extractor --output-dir "\\NAS\partage\succes"`
- Démarrer dans : `S:\Achievements`

## 2. Appli web (NAS)

Générer les secrets :

```bash
python scripts/generate_password_hash.py
python -c "import secrets; print('ACHIEVEMENTS_SECRET_KEY=' + secrets.token_hex(32))"
```

Copier `.env.example` en `.env` et y placer les deux lignes produites,
ajuster le chemin du dossier partagé dans le `docker-compose.yml`, puis :

```bash
docker compose up -d
```

Le tableau de bord écoute sur le port 8080. Le placer derrière votre reverse
proxy pour l'exposer via votre nom de domaine en HTTPS.

## Fonctionnement du dossier partagé

L'extracteur écrit `succes_<horodatage>.json`. L'appli le repère (toutes les
5 minutes par défaut), l'ingère, puis le déplace dans `importes/`. Un fichier
illisible part dans `erreurs/` sans interrompre le service. Les fichiers `.tmp`
en cours d'écriture sont ignorés.

Attention : ce dossier partagé est monté dans le conteneur en bind-mount sur
`/inbox`, pas en volume nommé. Contrairement à `/data` (volume nommé, que
Docker initialise automatiquement avec les bonnes permissions), un bind-mount
conserve les permissions définies côté NAS : le dossier doit donc être
accessible en écriture par l'UID 1000, celui de l'utilisateur `app` dans le
conteneur. Sans cela, l'appli pourra lire les exports mais échouera à les
déplacer vers `importes/` ou `erreurs/` — à vérifier avant le premier
déploiement réel sur le NAS.

## Limites connues

- Seuls les jeux **Steam** ayant déjà généré un cache local sont détectés
  (95 jeux sur la machine de référence, y compris des jeux désinstallés).
- Les icônes sont chargées depuis le CDN Steam par le navigateur du visiteur.
- Un succès déjà enregistré comme débloqué ne repasse jamais à verrouillé,
  même si un export plus ancien est ingéré ensuite.

## Évolutions prévues (v2)

- Extension Playnite déclenchant l'extraction à la fermeture d'un jeu
  (sur le modèle de l'intégration Ludusavi/Playnite `OnGameStopped`).
- Support d'autres launchers via Playnite.
