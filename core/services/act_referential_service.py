"""
Référentiel des actes (lot I4, décisions N1 / N2 du 10/10/2026) : catégories, actes et alias, **communs à tous les
pays**, gérés par l'admin global (consultation : admin territorial et chef de département technique).

À l'import, le libellé d'acte du fichier passe par la table d'alias (alias -> libellé de l'acte retenu), puis l'acte
est retrouvé par sa clé de libellé (writer_service._referentials). Les alias pointent donc toujours vers le libellé
**actuel** d'un acte :
- renommer un acte : l'ancien libellé devient un alias, les alias existants suivent le nouveau libellé ;
- fusionner des actes : les lignes de sinistres passent sur l'acte retenu, les libellés des actes fusionnés deviennent
  des alias, leurs alias suivent, puis ils sont supprimés.
Chaque modification est tracée (ReferenceChange, objet ACT, sans pays).
"""
from django.db import transaction
from django.db.models import Count, Q

from core.models import Act, ActAlias, ActCategory, ClaimLine, ReferenceChange
from importer.reconciliation.normalize import clean_text, text_key


class ReferentialError(Exception):
    """Modification refusée : message renvoyé tel quel."""


def _user_name(user):
    return f'{user.first_name} {user.last_name}'.strip() or user.username


def _log(user, act, summary, details):
    ReferenceChange.objects.create(country=None, object_type='ACT', object_id=act.id if act else None,
                                   label=act.label if act else '', summary=summary, details=details,
                                   user=user, user_name=_user_name(user))


def _aliases_by_act_key():
    out = {}
    for a in ActAlias.objects.all().order_by('alias_label'):
        out.setdefault(text_key(a.act_label), []).append({'id': a.id, 'label': a.alias_label})
    return out


def categories():
    rows = ActCategory.objects.annotate(acts_count=Count('acts', distinct=True),
                                        lines_count=Count('claim_lines', distinct=True)).order_by('label')
    return [{'id': c.id, 'label': c.label, 'acts': c.acts_count, 'lines': c.lines_count} for c in rows]


def list_acts(search='', category_id=None, unused=False, page=1, page_size=50):
    qs = Act.objects.select_related('category').annotate(lines_count=Count('claim_lines'))
    aliases = _aliases_by_act_key()
    if search:
        key = text_key(search)
        alias_targets = [k for k, items in aliases.items() if any(key in text_key(i['label']) for i in items)]
        qs = qs.filter(Q(label_key__icontains=key) | Q(label_key__in=alias_targets))
    if category_id:
        qs = qs.filter(category_id=category_id)
    if unused:
        qs = qs.filter(lines_count=0)
    total = qs.count()
    page_size = max(1, min(int(page_size), 200))
    page = max(1, int(page))
    acts = qs.order_by('label')[(page - 1) * page_size: page * page_size]
    return {'count': total, 'page': page, 'page_size': page_size, 'results': [{
        'id': a.id, 'label': a.label, 'category': {'id': a.category_id, 'label': a.category.label},
        'lines': a.lines_count, 'aliases': aliases.get(a.label_key, []),
    } for a in acts]}


def act_detail(act_id):
    a = Act.objects.select_related('category').filter(pk=act_id).first()
    if a is None:
        return None
    by_cat = list(ClaimLine.objects.filter(act=a).values('category__label').annotate(n=Count('id')).order_by('-n'))
    history = ReferenceChange.objects.filter(object_type='ACT', object_id=a.id)[:50]
    return {'id': a.id, 'label': a.label, 'category': {'id': a.category_id, 'label': a.category.label},
            'lines': sum(r['n'] for r in by_cat),
            'lines_by_category': [{'category': r['category__label'], 'lines': r['n']} for r in by_cat],
            'aliases': _aliases_by_act_key().get(a.label_key, []),
            'history': [{'summary': h.summary, 'user': h.user_name, 'date': h.created_at.isoformat()} for h in history]}


def _add_alias(alias_label, act_label):
    """Alias -> libellé de l'acte (crée ou redirige). Un alias identique au libellé retenu est inutile."""
    key = text_key(alias_label)
    if not key or key == text_key(act_label):
        return
    ActAlias.objects.update_or_create(alias_key=key, defaults={'alias_label': alias_label, 'act_label': act_label})


def _retarget(old_label, new_label):
    """Les alias qui pointaient vers `old_label` pointent vers `new_label` (et un alias devenu égal au libellé retenu
    est supprimé)."""
    old_key = text_key(old_label)
    for a in ActAlias.objects.all():
        if text_key(a.act_label) == old_key:
            if a.alias_key == text_key(new_label):
                a.delete()
            else:
                a.act_label = new_label
                a.save(update_fields=['act_label'])


@transaction.atomic
def update_act(user, act_id, data):
    act = Act.objects.select_for_update().select_related('category').filter(pk=act_id).first()
    if act is None:
        raise ReferentialError("Acte introuvable.")
    changes = []
    label = clean_text(data.get('label'))
    if label and label != act.label:
        key = text_key(label)
        other = Act.objects.filter(label_key=key).exclude(pk=act.pk).first()
        if other:
            raise ReferentialError(f"Un autre acte s'appelle déjà « {other.label} » : utilisez la fusion.")
        alias = ActAlias.objects.filter(alias_key=key).first()
        if alias and text_key(alias.act_label) != act.label_key:
            raise ReferentialError(f"« {label} » est déjà un alias de l'acte « {alias.act_label} ».")
        old = act.label
        act.label, act.label_key = label, key
        act.save(update_fields=['label', 'label_key', 'modification_date'])
        _retarget(old, label)
        if text_key(old) != key:
            _add_alias(old, label)
        else:
            ActAlias.objects.filter(alias_key=key).delete()
        changes.append(f"Acte « {old} » renommé « {label} » (l'ancien libellé devient un alias).")
    if data.get('category_id') and int(data['category_id']) != act.category_id:
        cat = ActCategory.objects.filter(pk=data['category_id']).first()
        if cat is None:
            raise ReferentialError("Catégorie introuvable.")
        old = act.category.label
        act.category = cat
        act.save(update_fields=['category', 'modification_date'])
        changes.append(f"Acte « {act.label} » : catégorie « {old} » -> « {cat.label} ».")
    if not changes:
        raise ReferentialError("Aucune modification à enregistrer.")
    for c in changes:
        _log(user, act, c, {})
    return {'detail': ' '.join(changes), 'act': act_detail(act.id)}


@transaction.atomic
def merge_acts(user, keep_id, absorb_ids):
    keep = Act.objects.select_for_update().filter(pk=keep_id).first()
    if keep is None:
        raise ReferentialError("Acte à conserver introuvable.")
    ids = {int(i) for i in absorb_ids or []} - {keep.id}
    if not ids:
        raise ReferentialError("Choisissez au moins un acte à fusionner dans « %s »." % keep.label)
    absorbed = list(Act.objects.select_for_update().filter(pk__in=ids))
    if len(absorbed) != len(ids):
        raise ReferentialError("Un des actes à fusionner est introuvable.")
    lines = ClaimLine.objects.filter(act__in=absorbed).update(act=keep)
    names = []
    for a in absorbed:
        _retarget(a.label, keep.label)
        _add_alias(a.label, keep.label)
        names.append(a.label)
        ReferenceChange.objects.filter(object_type='ACT', object_id=a.id).update(object_id=keep.id)
    Act.objects.filter(pk__in=ids).delete()
    summary = (f"{len(names)} acte(s) fusionné(s) dans « {keep.label} » : " + ', '.join(f"« {n} »" for n in names)
               + f" ; {lines} ligne(s) de sinistres reprises, libellés gardés comme alias.")
    _log(user, keep, summary, {'absorbed': names, 'lines': lines})
    return {'detail': summary, 'act': act_detail(keep.id)}


@transaction.atomic
def create_alias(user, act_id, alias_label):
    act = Act.objects.filter(pk=act_id).first()
    if act is None:
        raise ReferentialError("Acte introuvable.")
    label = clean_text(alias_label)
    if not label:
        raise ReferentialError("Saisissez le libellé de l'alias.")
    key = text_key(label)
    if key == act.label_key:
        raise ReferentialError("L'alias est identique au libellé de l'acte.")
    other = Act.objects.filter(label_key=key).first()
    if other:
        raise ReferentialError(f"« {label} » est le libellé de l'acte « {other.label} » : utilisez la fusion.")
    existing = ActAlias.objects.filter(alias_key=key).first()
    if existing and text_key(existing.act_label) != act.label_key:
        raise ReferentialError(f"« {label} » est déjà un alias de « {existing.act_label} ».")
    if existing:
        raise ReferentialError("Cet alias existe déjà pour cet acte.")
    ActAlias.objects.create(alias_key=key, alias_label=label, act_label=act.label)
    summary = f"Alias « {label} » ajouté à l'acte « {act.label} » (pour les prochains imports)."
    _log(user, act, summary, {'alias': label})
    return {'detail': summary, 'act': act_detail(act.id)}


@transaction.atomic
def delete_alias(user, alias_id):
    alias = ActAlias.objects.filter(pk=alias_id).first()
    if alias is None:
        raise ReferentialError("Alias introuvable.")
    act = Act.objects.filter(label_key=text_key(alias.act_label)).first()
    summary = f"Alias « {alias.alias_label} » de l'acte « {alias.act_label} » supprimé."
    alias.delete()
    _log(user, act, summary, {'alias': alias.alias_label})
    return {'detail': summary}
