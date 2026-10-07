"""
Désactivation d'un pays : demande à motif obligatoire, quorum de validations des
ADMIN_GLOBAL, décision directe du SUPERUSER, expiration et notifications par e-mail.

Règles (décidées le 07/10/2026) :
- un ADMIN_GLOBAL ne désactive pas directement : il crée une demande, qui compte
  comme sa propre validation ;
- quorum : 2 validations s'il y a au plus 3 ADMIN_GLOBAL actifs à la création de la
  demande, 3 au-delà ;
- chaque ADMIN_GLOBAL peut valider ou refuser (une fois) ; la demande est refusée dès
  que les refus rendent le quorum impossible, et expire après 7 jours ;
- le demandeur peut annuler sa demande ;
- le SUPERUSER désactive directement (motif obligatoire) et peut trancher une
  demande ; c'est aussi lui qui tranche s'il n'y a qu'un seul ADMIN_GLOBAL ;
- chaque étape est notifiée par e-mail aux autres ADMIN_GLOBAL et au SUPERUSER.
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from users.models import CustomUser
from users.utils import send_user_email
from .models import Country, CountryDeactivationRequest as Req, CountryDeactivationVote as Vote

logger = logging.getLogger(__name__)

REQUEST_LIFETIME = timedelta(days=7)


class DeactivationError(Exception):
    """Action impossible sur une demande ou un pays (message destiné à l'utilisateur)."""


# --------------------------------------------------------------------------- quorum
def active_global_admins():
    return CustomUser.objects.filter(role=CustomUser.Roles.ADMIN_GLOBAL, is_active=True)


def required_approvals_for(eligible_voters):
    return 2 if eligible_voters <= 3 else 3


def tally(req):
    votes = list(req.votes.all())
    approvals = sum(v.decision == Vote.Decision.APPROVE for v in votes)
    rejections = sum(v.decision == Vote.Decision.REJECT for v in votes)
    return approvals, rejections


def quorum_unreachable(req):
    """Vrai si, à cause des refus, le quorum ne peut plus être atteint par les ADMIN_GLOBAL."""
    approvals, rejections = tally(req)
    remaining = max(req.eligible_voters - approvals - rejections, 0)
    return rejections > 0 and approvals + remaining < req.required_approvals


# --------------------------------------------------------------------------- notifications
def _recipients(exclude=None):
    users = CustomUser.objects.filter(
        role__in=[CustomUser.Roles.ADMIN_GLOBAL, CustomUser.Roles.SUPERUSER], is_active=True
    )
    if exclude is not None:
        users = users.exclude(pk=exclude.pk)
    return list(users)


def _notify(subject, body, exclude=None):
    """E-mail à chaque ADMIN_GLOBAL actif et au SUPERUSER (sauf l'auteur de l'action),
    envoyé une fois la transaction validée (jamais si l'action est annulée).
    Un échec d'envoi est journalisé mais ne bloque jamais l'action."""
    recipients = _recipients(exclude)

    def send():
        for user in recipients:
            try:
                send_user_email(to_email=user.email, subject=subject,
                                plain_text_content=f"Bonjour {user.first_name},\n\n{body}\n\nSUNU DASH")
            except Exception as e:
                logger.warning("Notification désactivation pays non envoyée à %s : %s", user.email, e)

    transaction.on_commit(send)


def _who(user):
    return f"{user.first_name} {user.last_name} ({user.email})" if user else "un compte supprimé"


# --------------------------------------------------------------------------- expiration
def expire_overdue():
    """Passe en EXPIRED les demandes en attente dépassées (appelé avant chaque lecture/action)."""
    for req in Req.objects.filter(status=Req.Status.PENDING, expires_at__lte=timezone.now()).select_related('country'):
        req.status = Req.Status.EXPIRED
        req.decided_at = timezone.now()
        req.save(update_fields=['status', 'decided_at'])
        _notify(f"Demande de désactivation expirée — {req.country.name}",
                f"La demande de désactivation du pays {req.country.name} a expiré sans atteindre "
                f"le quorum ({tally(req)[0]}/{req.required_approvals} validations). Le pays reste actif.")


# --------------------------------------------------------------------------- actions
def _apply(req, actor, decided_by_superuser):
    country = req.country
    country.is_active = False
    country.save(update_fields=['is_active'])
    req.status = Req.Status.APPROVED
    req.decided_at = timezone.now()
    req.decided_by = actor
    req.save(update_fields=['status', 'decided_at', 'decided_by'])
    how = "par décision du SUPERUSER" if decided_by_superuser else \
        f"après {tally(req)[0]} validation(s) sur {req.required_approvals} requise(s)"
    _notify(f"Pays désactivé — {country.name}",
            f"Le pays {country.name} a été désactivé {how}.\nMotif : {req.reason}\n\n"
            f"Les comptes rattachés à ce pays sont gelés jusqu'à sa réactivation.",
            exclude=actor)


def request_or_deactivate(country, actor, reason):
    """
    ADMIN_GLOBAL → crée une demande (sa validation incluse) et renvoie (demande, False).
    SUPERUSER   → désactive directement et renvoie (demande, True).
    """
    reason = (reason or '').strip()
    if not reason:
        raise DeactivationError("Le motif de désactivation est obligatoire.")
    if not country.is_active:
        raise DeactivationError(f"Le pays {country.name} est déjà désactivé.")

    with transaction.atomic():
        expire_overdue()
        pending = Req.objects.select_for_update().filter(country=country, status=Req.Status.PENDING).first()

        if actor.is_superuser_role():
            req = pending or Req.objects.create(
                country=country, requested_by=actor, reason=reason,
                eligible_voters=active_global_admins().count(),
                required_approvals=required_approvals_for(active_global_admins().count()),
                expires_at=timezone.now() + REQUEST_LIFETIME,
            )
            if pending:  # le SUPERUSER tranche la demande en cours, avec son propre motif
                req.reason = f"{pending.reason}\n[Décision du SUPERUSER] {reason}"
            _apply(req, actor, decided_by_superuser=True)
            return req, True

        if pending:
            raise DeactivationError(
                f"Une demande de désactivation de {country.name} est déjà en attente : "
                f"validez-la ou refusez-la plutôt que d'en créer une nouvelle.")
        eligible = active_global_admins().count()
        req = Req.objects.create(
            country=country, requested_by=actor, reason=reason,
            eligible_voters=eligible, required_approvals=required_approvals_for(eligible),
            expires_at=timezone.now() + REQUEST_LIFETIME,
        )
        Vote.objects.create(request=req, admin=actor, decision=Vote.Decision.APPROVE, comment="Demandeur")

    note = (" Il n'y a qu'un seul administrateur global : seul le SUPERUSER peut trancher."
            if eligible <= 1 else "")
    _notify(f"Demande de désactivation — {country.name}",
            f"{_who(actor)} demande la désactivation du pays {country.name}.\nMotif : {reason}\n\n"
            f"Validations : 1/{req.required_approvals} (le demandeur compte). La demande expire le "
            f"{timezone.localtime(req.expires_at):%d/%m/%Y à %H:%M}.{note}\n"
            f"Connectez-vous à SUNU DASH, page « Pays », pour la valider ou la refuser.",
            exclude=actor)
    return req, False


def vote(req_id, actor, approve, comment=''):
    """Validation / refus d'une demande. SUPERUSER : sa décision clôt la demande."""
    with transaction.atomic():
        expire_overdue()
        req = Req.objects.select_for_update().select_related('country').filter(pk=req_id).first()
        if req is None:
            raise DeactivationError("Demande introuvable.")
        if req.status != Req.Status.PENDING:
            raise DeactivationError(f"Cette demande n'est plus en attente ({req.get_status_display().lower()}).")
        comment = (comment or '').strip()

        if actor.is_superuser_role():
            if approve:
                _apply(req, actor, decided_by_superuser=True)
            else:
                _close(req, actor, Req.Status.REJECTED,
                       f"Le SUPERUSER a refusé la demande de désactivation du pays {req.country.name}."
                       + (f"\nCommentaire : {comment}" if comment else ""))
            return req

        if req.votes.filter(admin=actor).exists():
            raise DeactivationError("Vous vous êtes déjà prononcé sur cette demande.")
        Vote.objects.create(request=req, admin=actor, comment=comment,
                            decision=Vote.Decision.APPROVE if approve else Vote.Decision.REJECT)
        approvals, rejections = tally(req)

        if approvals >= req.required_approvals:
            _apply(req, actor, decided_by_superuser=False)
        elif quorum_unreachable(req):
            _close(req, actor, Req.Status.REJECTED,
                   f"La demande de désactivation du pays {req.country.name} est refusée : "
                   f"avec {rejections} refus, le quorum de {req.required_approvals} validations "
                   f"ne peut plus être atteint. Le pays reste actif.")
        else:
            verb = "validé" if approve else "refusé"
            _notify(f"Demande de désactivation — {req.country.name} : {approvals}/{req.required_approvals}",
                    f"{_who(actor)} a {verb} la demande de désactivation du pays {req.country.name}."
                    + (f"\nCommentaire : {comment}" if comment else "")
                    + f"\nValidations : {approvals}/{req.required_approvals}, refus : {rejections}.",
                    exclude=actor)
        return req


def cancel(req_id, actor):
    with transaction.atomic():
        expire_overdue()
        req = Req.objects.select_for_update().select_related('country').filter(pk=req_id).first()
        if req is None:
            raise DeactivationError("Demande introuvable.")
        if req.status != Req.Status.PENDING:
            raise DeactivationError(f"Cette demande n'est plus en attente ({req.get_status_display().lower()}).")
        if req.requested_by_id != actor.pk and not actor.is_superuser_role():
            raise DeactivationError("Seul l'auteur de la demande (ou le SUPERUSER) peut l'annuler.")
        _close(req, actor, Req.Status.CANCELLED,
               f"{_who(actor)} a annulé la demande de désactivation du pays {req.country.name}. Le pays reste actif.")
        return req


def _close(req, actor, status, message):
    req.status = status
    req.decided_at = timezone.now()
    req.decided_by = actor
    req.save(update_fields=['status', 'decided_at', 'decided_by'])
    _notify(f"Demande de désactivation — {req.country.name} : {req.get_status_display().lower()}",
            message, exclude=actor)


def reactivate(country, actor):
    """Réactivation directe (ADMIN_GLOBAL ou SUPERUSER), qui lève le gel des comptes."""
    if country.is_active:
        return False
    country.is_active = True
    country.save(update_fields=['is_active'])
    return True
