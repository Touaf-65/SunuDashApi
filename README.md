# SunuDash — API

API du tableau de bord d'analyse d'assurance santé **SunuDash** (multi-pays).
Django 5.1 · Django REST Framework · JWT (SimpleJWT) · PostgreSQL 16 · Celery + Redis · pandas.

> Ce document décrit ce qui est **en place et vérifié** : installation locale, rôles, authentification,
> gestion des comptes et des pays. La chaîne d'**import des sinistres** est en cours de refonte
> (voir [État des modules](#état-des-modules)) ; son ancienne documentation, en partie obsolète,
> est conservée dans `README2.md`.

---

## Sommaire

1. [Installation locale](#installation-locale)
2. [Configuration (`.env`)](#configuration-env)
3. [Rôles et périmètres](#rôles-et-périmètres)
4. [Authentification](#authentification)
5. [Création et gestion des comptes](#création-et-gestion-des-comptes)
6. [Imports de comptes et de pays (Excel / CSV)](#imports-de-comptes-et-de-pays-excel--csv)
7. [Gestion des pays](#gestion-des-pays)
8. [Fichiers importés (sinistres) : sécurité](#fichiers-importés-sinistres--sécurité)
9. [Import des sinistres : lecture et rapprochement](#import-des-sinistres--lecture-et-rapprochement)
10. [Familles d'assurés](#familles-dassurés)
11. [E-mails envoyés](#e-mails-envoyés)
12. [Référence des routes](#référence-des-routes)
13. [Codes de réponse à connaître](#codes-de-réponse-à-connaître)
14. [État des modules](#état-des-modules)

---

## Installation locale

Prérequis : **Python 3.11**, **Docker Desktop** (PostgreSQL + Redis), Git.

```powershell
# 1. Environnement Python
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configuration : copier le modèle puis renseigner les valeurs (voir ci-dessous)
copy .env.example .env

# 3. Base de données et Redis
docker compose up -d

# 4. Schéma de la base
python manage.py migrate

# 5. Lancer l'API (http://127.0.0.1:8000)
python manage.py runserver
```

- Sans `DATABASE_URL`, l'API retombe sur le fichier SQLite `db.sqlite3`.
- **Windows Defender** (« Accès contrôlé aux dossiers ») peut empêcher Python d'écrire dans `Documents` :
  autoriser `python.exe` (Python 3.11) dans la protection contre les ransomware, ou placer le projet hors de `Documents`.
- Les tâches d'import utilisent **Celery** : en local, lancer un worker si nécessaire
  (`celery -A sunu_dash worker -l info --pool=solo` sous Windows).

---

## Configuration (`.env`)

Le fichier `.env` n'est **jamais versionné** ; `.env.example` sert de modèle.

| Variable | Rôle |
|---|---|
| `DJANGO_SECRET_KEY` | **Obligatoire** (l'API refuse de démarrer sans). Générer : `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` |
| `DJANGO_DEBUG` | `True` en local uniquement ; `False` par défaut |
| `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` | Hôtes autorisés, origines du frontend (ex. `http://localhost:4200`) |
| `DATABASE_URL` | Ex. `postgres://sunudash:<mot_de_passe>@localhost:5432/sunudash` |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Utilisés par `docker-compose.yml` |
| `FRONTEND_URL` | Base des liens envoyés par e-mail (ex. `http://localhost:4200` en local) |
| `EMAIL_BACKEND` | En local : `django.core.mail.backends.console.EmailBackend` (les e-mails s'affichent dans le terminal, rien n'est envoyé) |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Serveur SMTP en production |
| `CELERY_BROKER_URL` | Redis, ex. `redis://localhost:6379/0` |

---

## Rôles et périmètres

| Rôle | Périmètre | Peut notamment |
|---|---|---|
| `SUPERUSER` | Administration des comptes (pas de statistiques) | Gérer les **admins globaux** ; désactiver un pays **immédiatement** ; trancher une demande de désactivation ; réactiver un pays |
| `ADMIN_GLOBAL` | Tous les pays | Gérer les **pays** ; gérer les **admins territoriaux** et leur affectation ; **demander** la désactivation d'un pays (quorum) ; réactiver un pays |
| `ADMIN_TERRITORIAL` | **Son pays** | Gérer les **utilisateurs** de son pays (`CHEF_DEPT_TECH`, `RESP_OPERATEUR`) |
| `CHEF_DEPT_TECH` | Son pays | — |
| `RESP_OPERATEUR` | Son pays | — |

- Un admin territorial **sans pays affecté** n'a accès à aucun utilisateur.
- **Gel d'un pays désactivé** : les comptes rattachés à un pays désactivé (admin territorial, chef de département,
  opérateurs) n'ont plus accès à rien, y compris avec un jeton obtenu avant la désactivation
  (401, code `country_inactive`) ; leur connexion est refusée avec ce motif. Ils ne sont pas supprimés :
  tout revient à la réactivation du pays.

---

## Authentification

- **Jetons JWT** (`access_token` valable 12 h) obtenus par `POST /auth/login/` avec `{"login": "<identifiant ou e-mail>", "password": "…"}`.
  L'identifiant et l'e-mail sont acceptés, sans tenir compte de la casse.
- Toutes les routes protégées passent par `users.authentication.ActiveCountryJWTAuthentication`
  (authentification par défaut de DRF), qui ajoute :
  1. le **gel des comptes d'un pays désactivé** (401 `country_inactive`) ;
  2. le **changement de mot de passe obligatoire** à la première connexion (voir ci-dessous).
- **Routes publiques** (connexion, mot de passe oublié, confirmation, création du premier superuser) :
  elles ignorent l'en-tête `Authorization` — un jeton absent ou expiré envoyé par le navigateur ne provoque pas de 401.
- `GET /auth/getConnectedUser/<login>/` : **profil de l'utilisateur connecté uniquement** (404 pour tout autre compte,
  sans révéler s'il existe).
- `POST /auth/verify_password/` : confirmation par mot de passe avant une action sensible ;
  répond **200 `true`/`false`** (jamais 401 pour un mauvais mot de passe : la session reste ouverte).

### Mot de passe provisoire → changement obligatoire

- Tout compte **créé ou importé** reçoit un mot de passe généré, envoyé par e-mail, et le marqueur
  `must_change_password`.
- Tant qu'il n'est pas levé, **toute route** répond **403 `password_change_required`**, sauf
  `POST /auth/change_password/` et la lecture de son propre profil. La connexion renvoie `must_change_password: true`.
- `POST /auth/change_password/` : `{"old_password", "new_password", "confirm_password"}` ;
  règles de sécurité de Django (messages en français : trop court, trop courant, entièrement numérique…),
  nouveau différent de l'actuel, e-mail de confirmation **sans** le mot de passe.
- « **Mot de passe oublié** » (`password_reset` → lien `FRONTEND_URL/auth/new-password/<jeton>/`, valable 24 h,
  à usage unique → `password_reset_confirm`) lève aussi le marqueur.

---

## Création et gestion des comptes

| Qui | Crée / gère | Règles |
|---|---|---|
| Personne (une seule fois) | Premier `SUPERUSER` (`/auth/create_superuser/`) | Refusé dès qu'un superuser existe |
| `SUPERUSER` | `ADMIN_GLOBAL` | Création unitaire ou import ; modification nom/e-mail ; activation/désactivation ; suppression |
| `ADMIN_GLOBAL` | `ADMIN_TERRITORIAL` | Idem + **affectation** à un pays actif, réaffectation, désaffectation |
| `ADMIN_TERRITORIAL` | `CHEF_DEPT_TECH`, `RESP_OPERATEUR` **de son pays** | Idem ; **changement de rôle** entre ces deux rôles uniquement |

Règles communes à toutes les créations :
- **Le compte n'est créé que si l'e-mail d'identifiants part** : en cas d'échec d'envoi, la création est annulée (503 en
  création unitaire ; ligne listée dans `echecs_envoi_email` à l'import, qui continue).
- **Identifiant** généré : `prenom.nom` **sans accent ni espace** (« Komlan Agbéko » → `komlan.agbeko`,
  « Jean Marc N'Guessan » → `jean-marc.nguessan`) ; en cas d'homonyme, **nombre aléatoire 1-999** ajouté
  (`komlan.agbeko254`). Le nom affiché garde ses accents.
- **E-mail** : ASCII uniquement (aucun accent, ni dans la partie locale ni dans le domaine) et format valide ;
  unique sans tenir compte de la casse. Même contrôle à la modification.
- Création avec un e-mail déjà utilisé → **409**.
- **Rôles** : un changement de rôle est refusé par défaut ; seule la mise à jour des utilisateurs simples autorise
  `CHEF_DEPT_TECH` ↔ `RESP_OPERATEUR`. Aucune route ne permet de promouvoir un compte en admin ou superuser.
- **Activation / désactivation** (`/auth/users/<id>/toggle-active/`) : SUPERUSER → admins globaux ;
  ADMIN_GLOBAL → admins territoriaux ; ADMIN_TERRITORIAL → utilisateurs de son pays.
  Un compte désactivé ne peut plus se connecter.

---

## Imports de comptes et de pays (Excel / CSV)

Formats acceptés : **`.xlsx`, `.xls`, `.csv`** (`users.utils.read_import_file`).
CSV : UTF-8 (avec ou sans BOM) ou **Windows-1252** (Excel français) ; séparateur `;`, `,` ou tabulation détecté ;
cellules vides respectées ; espaces des en-têtes ignorés.

| Import | Route | Colonnes |
|---|---|---|
| Admins globaux (SUPERUSER) | `/auth/global_admins/import_create/` | `first_name`, `last_name`, `email`, `role` (facultatif : seules les variantes de « Administrateur Global » sont retenues) |
| Admins territoriaux (ADMIN_GLOBAL) | `/auth/territorial_admins/import_create/` | `firstname`, `lastname`, `email` |
| Utilisateurs (ADMIN_TERRITORIAL) | `/auth/territorial_admins/users/import_create_user/` | `firstname`, `lastname`, `email`, `role` (« Chef Département Technique », « chef », « Responsable Opérateur (de Saisie) », « ops »…) |
| Pays (ADMIN_GLOBAL) | `/countries/import_create/` | `name`, `code`, `currency_code` et `currency_name` (facultatifs, défaut XOF / F CFA) |

Réponse type : `message`, `created_count`, `lignes_ignores`, `echecs_envoi_email` (comptes) ou `skipped_rows`
(pays : numéro de ligne + raison). Réimporter le même fichier ne crée que ce qui manque.
Fichier vide, illisible, mal nommé ou sans les bonnes colonnes → **400** avec un message en français.

---

## Gestion des pays

- **Création / modification** (ADMIN_GLOBAL) : code de 1 à 4 lettres, en majuscules ; **nom et code uniques sans tenir
  compte de la casse ni des espaces**, garantis aussi par la base (index sur `LOWER(TRIM(name))` et `LOWER(TRIM(code))`) ;
  noms conservés **tels que saisis** (espaces nettoyés, première lettre en majuscule : « Côte d'Ivoire », « F CFA »).
- **Liste** : le SUPERUSER voit tous les pays ; l'ADMIN_GLOBAL voit les pays actifs par défaut
  (listes de choix) et tous avec `?include_inactive=true` (page de gestion). Chaque pays porte
  `pending_deactivation` (avancement d'une demande en cours, ou `null`).
- **Un pays n'est jamais supprimé** (clients, partenaires et sinistres y sont rattachés) : il est **désactivé**.

### Désactivation d'un pays (motif + quorum)

| Étape | Règle |
|---|---|
| Demande | Un ADMIN_GLOBAL demande la désactivation avec un **motif obligatoire** ; sa demande compte comme une validation |
| Quorum | **2** validations s'il y a au plus 3 ADMIN_GLOBAL actifs, **3** au-delà (figé à la création de la demande) |
| Avis | Chaque ADMIN_GLOBAL valide ou refuse une fois (commentaire facultatif) |
| Refus | La demande est refusée dès que les refus rendent le quorum impossible |
| Expiration | 7 jours sans quorum (passage à « expirée » à la consultation suivante) |
| Annulation | Par le demandeur |
| SUPERUSER | Désactive **immédiatement** (motif obligatoire) ; peut valider ou refuser toute demande ; seul recours s'il n'y a qu'un ADMIN_GLOBAL |
| Réactivation | ADMIN_GLOBAL ou SUPERUSER ; lève le gel des comptes du pays |
| Notifications | E-mail à chaque étape aux autres ADMIN_GLOBAL et au SUPERUSER |

- Une seule demande en attente par pays ; impossible d'affecter un admin territorial à un pays désactivé.
- Recréer un pays désactivé → 400 « … existe déjà mais est désactivé : réactivez-le plutôt que de le recréer ».
- Règles centralisées dans `countries/deactivation.py`.

---

## Fichiers importés (sinistres) : sécurité

Règles centralisées dans `file_handling/access.py`. Le traitement de l'import lui-même est encore en refonte.

| Action | Qui |
|---|---|
| Importer (fichier statistique + fichier récap) | ADMIN_TERRITORIAL ou CHEF_DEPT_TECH **rattaché à un pays** |
| Lister, télécharger, prévisualiser, lire le journal / rapport | ADMIN_TERRITORIAL et CHEF_DEPT_TECH **du pays du fichier** |
| Supprimer un import d'un **admin territorial** | Son auteur seulement ; si l'auteur n'est plus admin territorial du pays (réaffecté, désactivé, changé de rôle, supprimé) → les admins territoriaux actuels du pays |
| Supprimer un import d'un **chef de département technique** | Son auteur et les admins territoriaux du pays |

- **Isolement par pays** : pour un autre pays, un fichier ou une session répond **404** (comme s'il n'existait pas).
  Les autres rôles (RESP_OPERATEUR, ADMIN_GLOBAL, SUPERUSER) reçoivent **403**.
- La **suppression** porte toujours sur **l'import entier** : fichier statistique + tous les récaps + journal + rapport,
  en base et sur disque. Les sinistres qu'il a écrits en base restent, détachés de l'import, sauf si la requête
  demande `{"delete_claims": true, "password": "…"}` : le mot de passe de l'utilisateur connecté est alors vérifié
  par l'API (403 `invalid_password` sinon, rien n'est supprimé), puis les sinistres et leurs lignes sont supprimés.
  Les référentiels (assurés, polices, partenaires…) restent. `claims_count` (fichiers, sessions) donne leur nombre.
- Le **rôle de l'auteur** est enregistré au chargement (`uploaded_by_role`) : les droits ne changent pas si son compte change ensuite.
- **Contrôles à l'import** : `.xlsx`, `.xls`, `.csv` uniquement, **contenu vérifié** (un exécutable renommé est refusé),
  fichier non vide, **50 Mo maximum** par fichier (`IMPORT_FILE_MAX_SIZE`).
- Les fichiers **ne sont jamais servis par `/media/`** : uniquement par les routes ci-dessous, avec jeton. Les réponses de
  l'API n'exposent pas leur chemin sur le serveur ; `can_delete` indique au frontend s'il peut proposer la suppression.

---

## Import des sinistres : lecture et rapprochement

Code : `importer/reconciliation/` (sans accès à la base), `importer/services/analysis_service.py` (session) et
`importer/services/writer_service.py` (écriture en base). Deux temps : le **rapprochement** (aucune écriture dans
les tables métier, rapport Excel), puis, sur action de l'utilisateur, l'**écriture en base** des sinistres importables.

1. **Dépôt** : un fichier statistique et **un ou plusieurs récaps** (pages d'un même export ; jusqu'à
   `IMPORT_MAX_RECAP_FILES` = 300 fichiers et `IMPORT_MAX_TOTAL_SIZE` = 200 Mo par envoi). Les fichiers verrous d'Excel
   (`~$…`) sont ignorés.
2. **Feuille** : si le fichier statistique a plusieurs feuilles et qu'aucune n'est donnée, la session passe en
   `AWAITING_SHEET` et la réponse liste les feuilles ; le choix se fait par `/import-sessions/<id>/analyse/`.
3. **Nature des fichiers** reconnue par leurs colonnes (fichiers inversés, colonne obligatoire absente ou sans titre → arrêt).
4. **Correspondance des colonnes** vers des noms communs (`columns.py`) ; dates (série Excel, `jj-mm-aaaa`…) et montants normalisés.
5. **Récaps** fusionnés, lignes strictement identiques retirées ; sinistres sans date de règlement = **non payés** (exclus, listés).
6. **Période commune** sur la date de règlement ; aucune → arrêt (statut `ERROR`), message avec les deux plages.
7. **Rapprochement** par sinistre (somme des lignes d'actes de la statistique contre le total du récap, tolérance < 5) :
   conforme, annulé (contre-passation à total nul), écart de montant, absent du récap, doublon divergent du récap,
   lignes illisibles, sinistre incohérent (deux bénéficiaires, polices… pour un même numéro). Statut `ANALYSED`,
   chiffres dans `summary`, rapport dans `error_file` (`?type=error`).
8. **Écriture en base** (`POST /import-sessions/<id>/import/`) : les fichiers sont relus et le même rapprochement
   refait, puis tout est écrit **en une transaction** (une panne n'écrit rien). Statut `DONE`, rapport complété.
   - Tout est **cloisonné par pays** : employeurs, polices, assurés, partenaires, opérateurs, factures, paiements et
     numéros de sinistre sont uniques dans un pays (clés normalisées).
   - Un sinistre = un en-tête + ses **lignes d'actes**, qui portent les montants (devise de la session).
   - **Familles** : principal au sein d'une police ; assuré retrouvé par `Broker_SunuId`, sinon par son nom sans
     accents, casse ni ordre des mots ; fautes d'orthographe signalées, jamais fusionnées ; principal sans
     consommation créé « déduit » ; rôle (principal / conjoint / enfant) porté par l'**adhésion** (`InsuredEmployer`).
   - **Polices** : plusieurs employeurs, souscripteur (entreprise ou particulier) déduit, plans de garanties,
     taux de couverture observé (un taux saisi n'est jamais remplacé).
   - **Actes** : variantes ramenées au libellé retenu par la table `ActAlias` ; « Famille Acte » gardée comme
     libellé de garantie sur la ligne.
   - **Réimport** : sinistre déjà en base identique → ignoré ; différent → rejeté et listé (jamais écrasé).

Pour essayer sur des fichiers locaux, sans passer par l'interface :

```bash
python manage.py analyse_import --stat "Stat.xlsx"                       # liste les feuilles
python manage.py analyse_import --stat "Stat.xlsx" --feuille "Janv - Déc + Tardifs" \
    --recap ../Donnees_SUNU/Recap --rapport rapport.xlsx
```

---

## Familles d'assurés

Une famille = un **assuré principal sur une police** et ses bénéficiaires (conjoints, enfants) sur cette police
(adhésions `InsuredEmployer` : rôle `primary`, ou `primary_insured_ref` = ce principal). Un principal présent sur deux
polices a deux familles. Réservé à l'**admin territorial** et au **chef de département technique**, familles de
**leur pays** (autre pays : 404). Code : `core/services/family_service.py`, `core/family_views.py`.

- **Lecture** : liste (recherche par le nom de n'importe quel membre, mots dans n'importe quel ordre, ou n° de carte ;
  filtres police, employeur, période de règlement ; tris ; pagination), fiche (membres, consommation par membre, par
  catégorie d'acte et par mois, sinistres avec leurs lignes, historique des corrections).
- **Corrections** : rattacher un bénéficiaire à un autre principal de la police ; changer un rôle (un principal qui
  devient bénéficiaire ne doit plus avoir de bénéficiaires) ; fusionner deux fiches de la même personne (refus si
  n° de carte différents, si l'une est bénéficiaire de l'autre, ou si leurs rôles diffèrent sur une même adhésion) ;
  choisir le nom retenu parmi les écritures connues.
  - Corps JSON avec `password` : mot de passe de l'utilisateur connecté, vérifié **avant** toute modification
    (403 `invalid_password`) ; refus métier → 400 avec le motif.
  - Chaque correction est tracée (`FamilyChange` : qui, quand, quoi, familles touchées).
  - Un réimport ne défait pas les corrections (rôle et principal d'une adhésion existante jamais modifiés ; personne
    retrouvée par son nom retenu ou ses autres écritures).
- Pas de plafond de consommation pour l'instant (champ `consumption_limit` non utilisé).

---

## E-mails envoyés

| Événement | Destinataire | Contenu |
|---|---|---|
| Création d'un compte | Le nouveau compte | Identifiant, mot de passe provisoire, obligation de le changer à la 1re connexion |
| Connexion réussie | L'utilisateur | Date, adresse IP |
| Mot de passe oublié | L'utilisateur | Lien de réinitialisation (24 h) |
| Mot de passe modifié / réinitialisé | L'utilisateur | Confirmation, **sans** le mot de passe |
| Affectation / réaffectation à un pays | L'admin territorial | Pays concerné |
| Désactivation de pays (demande, avis, décision, refus, annulation, expiration) | Autres ADMIN_GLOBAL + SUPERUSER | Pays, motif, avancement du quorum |

Aucun mot de passe n'est jamais écrit sur disque ni journalisé.

---

## Référence des routes

### Authentification et comptes — `/auth/`
| Méthode | Route | Accès |
|---|---|---|
| POST | `login/` | Public |
| POST | `password_reset/`, `password_reset_confirm/` | Public |
| POST | `create_superuser/` | Public, une seule fois |
| GET | `getConnectedUser/<login>/` | Connecté (son propre profil) |
| POST | `verify_password/`, `change_password/` | Connecté |
| POST | `users/<id>/toggle-active/` | Selon le rôle (voir plus haut) |
| GET / POST / PUT / DELETE | `global_admins/list/`, `create/`, `import_create/`, `<id>/`, `<id>/update/`, `<id>/delete/` | SUPERUSER |
| GET / POST / PUT / DELETE | `territorial_admins/list/`, `create/`, `import_create/`, `<id>/`, `<id>/update/`, `<id>/delete/`, `assign/`, `change_assign/` | ADMIN_GLOBAL |
| GET / POST / PUT / DELETE | `territorial_admins/users/list/`, `create_user/`, `import_create_user/`, `<id>/`, `<id>/update/`, `<id>/delete/` | ADMIN_TERRITORIAL avec pays |

### Pays — `/countries/`
| Méthode | Route | Accès |
|---|---|---|
| GET | `list/` (`?include_inactive=true`), `<id>/` | SUPERUSER, ADMIN_GLOBAL |
| POST / PUT | `create/`, `import_create/`, `<id>/update/` | ADMIN_GLOBAL |
| POST | `<id>/deactivate/` (`{"reason"}`) | ADMIN_GLOBAL (demande) ou SUPERUSER (immédiat) |
| POST | `<id>/restore/` | ADMIN_GLOBAL, SUPERUSER |
| GET | `deactivation-requests/` (`?status=PENDING` par défaut, ou `ALL`…) | ADMIN_GLOBAL, SUPERUSER |
| POST | `deactivation-requests/<id>/approve/`, `reject/` (`{"comment"}`), `cancel/` | ADMIN_GLOBAL, SUPERUSER |

### Fichiers et imports — `/data/`, `/files/`, `/import-sessions/`
| Méthode | Route | Accès |
|---|---|---|
| POST | `/data/upload/` (multipart `stat_file`, `recap_files` × n, `stat_sheet` et `currency` facultatifs) → 200 (`ANALYSED` ou `AWAITING_SHEET` + `sheets`), 422 si l'analyse s'arrête | ADMIN_TERRITORIAL, CHEF_DEPT_TECH avec pays |
| GET | `/import-sessions/<id>/sheets/` | ADMIN_TERRITORIAL, CHEF_DEPT_TECH du pays |
| POST | `/import-sessions/<id>/analyse/` (`{"stat_sheet"}`) : rapprochement ou nouveau rapprochement | Mêmes droits que la suppression |
| POST | `/import-sessions/<id>/import/` : écriture en base d'une session `ANALYSED` (409 sinon) | Mêmes droits que la suppression |
| GET | `/files/`, `/files/<id>/download/`, `/files/<id>/preview/` | ADMIN_TERRITORIAL, CHEF_DEPT_TECH du pays |
| DELETE | `/files/<id>/delete/` (supprime l'import entier du fichier) | Voir les règles de suppression |
| GET | `/import-sessions/`, `/import-sessions/<id>/download/?type=log` ou `?type=error` | ADMIN_TERRITORIAL, CHEF_DEPT_TECH du pays |
| DELETE | `/import-sessions/<id>/delete/` | Voir les règles de suppression |

### Familles — `/families/` (ADMIN_TERRITORIAL, CHEF_DEPT_TECH, familles de leur pays)
| Méthode | Route |
|---|---|
| GET | `/families/?search=&policy=&employer=&start=&end=&ordering=&page=&page_size=` (ordering : `name`, `policy`, `-reimbursed`, `-claims`, `-members`) |
| GET | `/families/filters/` (polices et employeurs du pays) |
| GET | `/families/<police>/<principal>/?start=&end=` (fiche) ; `/families/<police>/<principal>/claims/?member=&page=` |
| GET | `/families/<police>/principals/?search=&exclude=` ; `/families/insureds/?search=&exclude=` (choix d'un principal / d'une fiche) |
| POST | `/families/<police>/members/<assuré>/attach/` `{"principal_id", "password"}` |
| POST | `/families/<police>/members/<assuré>/role/` `{"role": "primary"\|"spouse"\|"child"\|"other", "principal_id", "password"}` |
| POST | `/families/insureds/merge/` `{"keep_id", "absorb_id", "password"}` ; `/families/insureds/<assuré>/name/` `{"name", "password"}` |

---

## Codes de réponse à connaître

| Code | Signification | Réaction attendue du frontend |
|---|---|---|
| 401 | Non connecté, jeton invalide/expiré, compte désactivé, **pays désactivé** (`code: country_inactive`) | Retour à la connexion |
| 403 `password_change_required` | Mot de passe provisoire pas encore changé | Redirection vers le changement de mot de passe (session conservée) |
| 403 | Action interdite pour ce rôle | Afficher l'erreur, **sans** déconnecter |
| 409 | E-mail déjà utilisé | Afficher le motif |
| 503 | Compte non créé : l'e-mail d'identifiants n'a pas pu partir | Réessayer plus tard |
| 204 | Suppression réussie (réponse **sans corps**) | — |

---

## État des modules

| Module | État |
|---|---|
| Comptes, authentification, rôles | ✅ Revu et testé (tests de bout en bout par HTTP réel) |
| Pays (y compris désactivation au quorum et gel) | ✅ Revu et testé |
| Sécurité des fichiers importés (`file_handling`) | ✅ Revue et testée |
| Import des sinistres (`importer`, `core`) | ✅ Lecture, rapprochement, rapport et écriture en base (I1-I3) ; suivi en tâche de fond à venir (I4) |
| Familles d'assurés (`core`) | ✅ Consultation et corrections tracées (F1) ; plafonds non gérés |
| Multi-devises | 📐 Conception arrêtée (devises par pays, taux datés saisis par les admins, devise choisie à l'import) — à développer |
| Tableaux de bord et statistiques (`dashboard`) | 🔧 Adaptés au nouveau modèle des sinistres (toutes les routes vérifiées après un import réel) ; revue complète à venir |
