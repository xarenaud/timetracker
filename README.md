# CX-Media TimeTracker v4

Application de suivi du temps — CX-Media

## Installation (nouveau Mac)

```bash
# 1. Extraire l'archive dans un dossier
# 2. Ouvrir le Terminal dans ce dossier

pip3 install -r requirements.txt
python3 app.py
```

## Accès

- **Local** : http://127.0.0.1:8080
- **iPhone (même Wi-Fi)** : http://[IP-du-Mac]:8080

## Identifiants par défaut

- **Login** : admin
- **Mot de passe** : admin123

⚠️ Changer le mot de passe admin après la première connexion !

## Fonctionnalités

- ⏱ Timer avec Pause/Reprise
- 👥 Sessions partagées (collègues)
- 📋 Historique avec filtres avancés
- ⚙️ Panel admin complet
- 🏷️ Catalogue de prestations
- 📊 Suivi des quotas mensuels
- ✏️ Encodage manuel

## Structure

```
timetracker/
├── app.py              # Application principale
├── requirements.txt    # Dépendances Python
├── timetracker.db      # Base de données (créée au 1er lancement)
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── index.html      # Timer
│   ├── records.html    # Historique
│   └── admin.html      # Administration
└── static/
    ├── css/style.css
    └── img/            # Placer logo.png ici
```

## Accès iPhone

1. Mac et iPhone sur le même Wi-Fi
2. Trouver l'IP du Mac : Préférences Système → Réseau
3. Accéder à : http://[IP-Mac]:8080

## Déploiement futur

- Railway (hébergement cloud)
- Sous-domaine : time.cx-media.be
- PWA pour installation mobile
# timetracker
