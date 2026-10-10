## Nomenclature des services
- Tous les services et vue qui recuperent des donnees sans filtre sur le pays, comme la liste des clients de tous les pays doivent commencer par Global
- Tous les services et vues qui recuperent des donnees sur un pays specifique doivent commencer par Country; par exemple: CountryClientsStatistics
- Tous les services et vue qui recupere les statistics doivent etre en statistics par exemple GlobalClientsStatistics
- Tous les services et vue qui recuperent les listes d'elements doivent etre en list par exemple: GlobalClientsList
- les urls pour des stats globales commencent par global

## Organisation (revue des tableaux de bord, lots D1 à D5, 10/10/2026)
- `access.py` : règle d'accès unique (`StatisticsAccess`) de toutes les vues : admin global = tout ; admin territorial
  et chef de département technique = leur pays (pays, employeur, police, prestataire, assuré, opérateur de l'URL
  contrôlés) ; vues `global_only` = admin global ; vues `operator_view` = aussi le responsable opérateur de son pays.
- `services/indicators.py` : définitions communes des indicateurs (sommes de la période sur la date de règlement,
  assurés ayant consommé, inscrits à part, nouveaux = premier sinistre, prime et S/P de `core/services/premium_service`,
  évolution par rapport à la période précédente de même durée, séries à 0 dans une tranche vide). Tout nouvel
  indicateur doit en partir.
- `services/country_statistics.py` : `ScopeStatisticsService`, commun aux tableaux de bord pays et multi-pays
  (`global_statistics.py`).
- `services/directory_service.py` + `directory_views.py` : listes et fiches des assurés, prestataires et opérateurs.
- `services/base.py` : périodes (tranches alignées sur le 1er du mois / trimestre / année), libellés, formats.
- Les erreurs de calcul ne sont jamais avalées : elles remontent (journal avec trace, réponse 500).
