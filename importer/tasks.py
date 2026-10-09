"""
Tâches Celery de l'import des sinistres.

L'ancienne tâche `async_import_data` (DataMapper) a été retirée au lot I3 (09/10/2026) : le rapprochement et
l'écriture en base passent par importer/services/analysis_service.py. Leur passage en tâche de fond, avec le suivi
d'import dans l'interface, est prévu au lot I4.
"""
