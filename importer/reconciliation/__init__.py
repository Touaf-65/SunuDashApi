"""
Lecture, identification et rapprochement des fichiers d'import des sinistres (lots I1 et I2, 09/10/2026).

Aucune écriture en base ici : ce paquet ne dépend que de pandas. Il est utilisé par l'API
(importer/services/analysis_service.py) et par la commande `python manage.py analyse_import`.

- normalize.py : textes, noms, montants et dates dans tous les formats rencontrés
- columns.py   : noms de colonnes des deux fichiers -> noms communs, reconnaissance de la nature d'un fichier
- sources.py   : lecture des fichiers (feuilles, CSV, plusieurs récaps) et préparation des données
- engine.py    : période commune et classement de chaque sinistre
- report.py    : rapport Excel
"""
