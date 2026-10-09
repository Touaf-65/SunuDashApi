"""
Rapprochement d'un fichier statistique et de récaps, sans rien écrire en base (lots I1 et I2).

    python manage.py analyse_import --stat "Stat.xlsx" --feuille "Janv - Déc + Tardifs" \
        --recap ../Donnees_SUNU/Recap --rapport rapport.xlsx

--recap accepte des fichiers et des dossiers (tous les .xlsx / .xls / .csv du dossier, fichiers verrous
d'Excel ignorés). Sans --feuille, la commande liste les feuilles du fichier statistique.
"""
import glob
import os
import re
import time

from django.core.management.base import BaseCommand, CommandError

from importer.reconciliation import engine, report, sources


def _natural(path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', os.path.basename(path))]


class Command(BaseCommand):
    help = "Rapprochement statistique / récaps et rapport Excel, sans écriture en base."

    def add_arguments(self, parser):
        parser.add_argument('--stat', required=True, help='Fichier statistique')
        parser.add_argument('--feuille', help='Feuille du fichier statistique')
        parser.add_argument('--recap', nargs='+', help='Fichiers récap et/ou dossiers de récaps')
        parser.add_argument('--rapport', help='Chemin du rapport Excel à écrire')
        parser.add_argument('--tolerance', type=float, default=engine.TOLERANCE)

    def handle(self, *args, **opts):
        stat_path = opts['stat']
        if not os.path.isfile(stat_path):
            raise CommandError(f"Fichier introuvable : {stat_path}")
        sheets = sources.list_sheets(stat_path)
        if not opts['feuille'] and len(sheets) > 1:
            self.stdout.write("Feuilles du fichier statistique (choisir avec --feuille) :")
            for name in sheets:
                self.stdout.write(f"  - {name}")
            return
        if not opts['recap']:
            raise CommandError("--recap est obligatoire pour le rapprochement.")
        sheet = opts['feuille'] or (sheets[0] if sheets else None)

        recap_files = []
        for item in opts['recap']:
            if os.path.isdir(item):
                found = [p for ext in ('*.xlsx', '*.xls', '*.csv') for p in glob.glob(os.path.join(item, ext))]
                recap_files += sorted(found, key=_natural)
            elif os.path.isfile(item):
                recap_files.append(item)
            else:
                raise CommandError(f"Récap introuvable : {item}")

        t0 = time.time()
        try:
            stat = sources.load_stat(stat_path, sheet=sheet)
            self.stdout.write(f"Statistique lue : {len(stat.data)} lignes ({time.time() - t0:.0f} s)")
            t1 = time.time()
            recap = sources.load_recaps([(p, None) for p in recap_files])
            self.stdout.write(f"Récaps lus : {len(recap.files)} fichiers, {len(recap.data)} lignes ({time.time() - t1:.0f} s)")
            result = engine.reconcile(stat, recap, tolerance=opts['tolerance'])
        except (sources.SourceError, engine.NoCommonPeriod, engine.NoUsableData) as exc:
            raise CommandError(str(exc))

        s = result.summary
        self.stdout.write(f"Période commune : {engine.fmt_date(result.period[0])} -> {engine.fmt_date(result.period[1])}")
        for cat, n in s['claims']['by_category'].items():
            self.stdout.write(f"  {cat:35} {n}")
        self.stdout.write(f"  {'Seulement dans le récap':35} {s['claims']['recap_only']}")
        self.stdout.write(f"Hors période : {s['out_of_period']['lines']} lignes ({s['out_of_period']['claims']} sinistres)")
        self.stdout.write(f"Récaps : {s['recap']['duplicate_rows_removed']} lignes identiques retirées, "
                          f"{s['recap']['unpaid']} non payés, {s['recap']['divergent_claims']} doublons divergents")
        imp = s['importable']
        self.stdout.write(f"Importables : {imp['claims']} sinistres, {imp['lines']} lignes, "
                          f"facturé {engine.fmt_amount(imp['claimed'])}, remboursé {engine.fmt_amount(imp['reimbursed'])}")

        if opts['rapport']:
            t2 = time.time()
            content = report.build_report(result, {'sheet': sheet, 'user': 'commande analyse_import'})
            with open(opts['rapport'], 'wb') as fh:
                fh.write(content)
            self.stdout.write(f"Rapport écrit : {opts['rapport']} ({len(content) // 1024} Ko, {time.time() - t2:.0f} s)")
        self.stdout.write(f"Durée totale : {time.time() - t0:.0f} s")
