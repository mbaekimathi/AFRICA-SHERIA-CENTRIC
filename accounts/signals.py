"""Signal hooks for Google Drive folder provisioning."""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Client

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Client)
def ensure_client_drive_folders_on_save(sender, instance: Client, **kwargs):
    """
    When a client becomes active/suspended and Drive is connected,
    create Clients/{name}/Litigation and Non-Litigation.
    """
    if instance.status not in {
        Client.Status.ACTIVE,
        Client.Status.SUSPENDED,
    }:
        return
    if (
        instance.drive_folder_id
        and instance.drive_litigation_folder_id
        and instance.drive_non_litigation_folder_id
    ):
        return

    try:
        from .google_drive import (
            GoogleDriveAPIError,
            GoogleDriveOAuthError,
            GoogleDriveConnection,
            ensure_client_folder_structure,
        )
    except Exception:
        return

    connection = GoogleDriveConnection.get_solo()
    if not connection.is_connected or not connection.clients_folder_id:
        return

    try:
        ensure_client_folder_structure(instance)
    except (GoogleDriveAPIError, GoogleDriveOAuthError) as exc:
        logger.warning(
            "Drive folder create skipped for client %s: %s", instance.pk, exc
        )
