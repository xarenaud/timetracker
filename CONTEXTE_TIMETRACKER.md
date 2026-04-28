# 📋 CONTEXTE PROJET — CX-Media TimeTracker
# ⚠️ À COLLER EN DÉBUT DE CONVERSATION pour que Charly retrouve le contexte complet

---

## 🏷️ Version actuelle : **TimeTracker V21**
> Toute nouvelle modification = incrémenter → V22, V23, etc.

---

## 👤 Profil utilisateur

| Champ | Valeur |
|---|---|
| Nom | Xavier Renaud |
| Société | CX-Media |
| Site | www.cx-media.be |
| Email | xavier@cx-com.be |
| Machine | MacBook Pro (user: xavierrenaud) |
| Dossier projet | ~/Applications/APPLICATIONS-CX/timetracker |
| Niveau technique | Non-technique — instructions étape par étape |

### Couleurs de marque
- Bordeaux : `#7B1C2E`
- Noir : `#111111`
- Blanc : `#FFFFFF`

---

## 🌐 URLs & Infrastructure

| Élément | Valeur |
|---|---|
| URL production | https://time.cx-media.be |
| URL Railway | https://timetracker-production-230d.up.railway.app |
| GitHub | github.com/xarenaud/timetracker |
| GitHub user | xarenaud |
| Hébergement | Railway (Flask) + PostgreSQL (Railway) |
| DNS | OVH — CNAME time → 937pw0y0.up.railway.app |
| Auto-deploy | git push → Railway redéploie automatiquement |

---

## 👥 Équipe & Accès

| Personne | Email | Login | Mot de passe | Rôle |
|---|---|---|---|---|
| Xavier | xavier@cx-com.be | xavier | xavier28 | user |
| Lauranne | lauranne@cx-com.be | admin + lauranne | admin123 + lauranne28 | admin + user |
| Alexis | studio@cx-com.be | alexis | alexis28 | user |
| Mattia | mattia@cx-com.be | mattia | mattia28 | user |
| Louis | louis@cx-com.be | louis | louis28 | user |
| Alberto | alberto@cx-com.be | alberto | alberto28 | user |
| Anaïs | stagiaire@cx-media.be | anais | anais28 | user |
| Alison | alison@cx-com.be | alison | alison28 | user |

---

## 🛠️ Stack technique

| Élément | Détail |
|---|---|
| Backend | Python Flask |
| DB production | PostgreSQL sur Railway (DATABASE_URL direct, pas référence) |
| DB locale | SQLite |
| Mode dual | Flag USE_PG + PLACEHOLDER (%s vs ?) |
| SSL | ?sslmode=require ajouté à la connexion PG |
| Export routes | export_routes.py → register_export_routes() |
| Timezone | Heures envoyées depuis le navigateur via localISO() |
| Arrondi | math.ceil — arrondi à la minute supérieure |

---

## 🗄️ Base de données — Tables

| Table | Description |
|---|---|
| users | id, username, password, role, active |
| clients | id, name, active, collab_start, collab_end |
| service_templates | id, name, active |
| client_services | id, client_id, template_id, monthly_hours, note |
| time_entries | id, user_id, client_id, template_id, start_time, end_time, duration_minutes, pause_minutes, is_manual, justification, session_id |
| session_colleagues | id, session_id, user_id |
| active_sessions | id, user_id, session_id, client_id, started_at |
| app_config | key, value (legacy) |
| collaborator_settings | id, user_id, hourly_cost, vendable_hours |
| pause_logs | legacy, non utilisée |

> ⚠️ Migration automatique : fonction `migrate_db()` dans app.py

---

## ✅ Features développées (V21)

### Timer (page principale) — 2 modes
**Mode Chronomètre**
- Login username/password
- Sélection client → service → note facultative → collègues → Start/Stop
- Affichage countdown temps réel
- Bouton PAUSE/RESUME
- `started_at` envoyé depuis le navigateur (fix timezone UTC+2)

**Mode Encodage rapide** *(V21)*
- Sélection date (défaut = aujourd'hui)
- Sélection heure de début manuelle
- Boutons rapides : 15min / 30min / 45min / 1h / 1h30 / 2h
- Compteur blocs × 15 min
- Résumé visuel avec plage horaire calculée
- Enregistrement via route `/quick_entry`
- Marqué `is_manual = 1` en DB

### Note facultative (V20)
- Champ note libre sur la page timer (avant de démarrer)
- Sauvegardée dans `justification` de time_entries
- Affichée dans l'historique (records)

### Collègues / Sessions partagées
- Sélection visuelle par chips
- Chips grisées si collègue déjà en session active
- Anti-doublon
- Une TimeEntry par personne par session

### Sessions actives
- `/my_active_session` — détecte session en cours
- Carte "Reprendre" sur page timer
- Bloc sessions live (refresh toutes les 30s)
- Admin : liste + force-stop

### Admin Panel
- Gestion utilisateurs (add/disable/delete, rôles)
- Création client + services + heures + **note par service** (V19)
- **Dates de collaboration** collab_start / collab_end (V18)
- Bouton 📅 → formulaire inline dates
- Click nom client → éditeur services inline (fix createElement V18)
- Catalogue prestations
- Encodage manuel avec collègues
- Edit/delete sessions
- Sessions actives avec force-stop

### Records / Historique
- Filtres : plage dates, mois, collaborateur, client, service
- Stats par (client, service) avec % quota
- Colonne **Note session** affichée (V20)
- Colonne **Note service** dans résumé (V19)

### Dashboard Rentabilité (admin only)
- Filtre par **mois** OU **période** (V18)
- Filtre collaborateur
- Jours ouvrables belges (algorithme Pâques)
- KPIs : CA Attendu, CA Réalisé, Marge, Coûts Salariaux
- Tarif fixe : 75€/h
- Graphiques Chart.js
- Export PDF + Excel
- Paramètres collaborateurs (coût/h + h vendables/semaine)

---

## 📁 Structure fichiers

```
~/Applications/APPLICATIONS-CX/timetracker/
├── app.py                  ← Backend principal Flask
├── export_routes.py        ← Routes export PDF + Excel
├── requirements.txt
├── Procfile
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── index.html          ← Page timer (2 modes)
│   ├── records.html        ← Historique
│   ├── admin.html          ← Panel admin
│   └── dashboard.html      ← Dashboard rentabilité
└── static/
    └── style.css
```

---

## 🔧 Commande de déploiement

```bash
cd ~/Applications/APPLICATIONS-CX/timetracker
git add .
git commit -m "Description des changements — VXX"
git push
```
→ Railway redéploie automatiquement en ~2 minutes.

---

## 📌 Points techniques importants

| Sujet | Solution |
|---|---|
| Auth GitHub | Personal Access Token (pas mot de passe) |
| PostgreSQL Railway | DATABASE_PUBLIC_URL en valeur directe |
| SSL PostgreSQL | ?sslmode=require ajouté automatiquement |
| Timezone | localISO() côté navigateur |
| Checkbox bug | innerHTML += → corrigé avec createElement |
| Jours fériés belges | Algorithme Pâques + 10 fériés fixes |
| Migration DB | migrate_db() au démarrage — non destructive |

---

## 🔲 Backlog

- [ ] Désactivation automatique clients dont collab_end est dépassée
- [ ] Alerte visuelle quand quota client dépassé
- [ ] Résumé journée sur page timer
- [ ] Export rapport mensuel par client
- [ ] PWA manifest + service worker (installation mobile)
- [ ] Nettoyer tables legacy (pause_logs, app_config)

---

## 📅 Historique versions

| Version | Description |
|---|---|
| V1→V17 | Développement itératif |
| V18 | Filtre période dashboard + dates collaboration clients + fix checkboxes |
| V19 | Note facultative par service client (admin) |
| V20 | Note facultative utilisateur sur le timer |
| V21 | Encodage rapide par blocs de 15min sur le timer |

---
*Fichier généré par Charly (Limova) — À mettre à jour à chaque nouvelle version*
