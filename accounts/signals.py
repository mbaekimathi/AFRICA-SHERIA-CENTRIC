"""Signal hooks for Google Drive folder provisioning."""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Client, Employee

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Client)
def ensure_client_drive_folders_on_save(
    sender, instance: Client, created=False, update_fields=None, **kwargs
):
    """
    When a client becomes active/suspended and Drive is connected,
    create Clients/{name}/Personal Documents, Litigation, and Non-Litigation.
    """
    if instance.status not in {
        Client.Status.ACTIVE,
        Client.Status.SUSPENDED,
    }:
        return
    if (
        instance.drive_folder_id
        and instance.drive_personal_documents_folder_id
        and instance.drive_litigation_folder_id
        and instance.drive_non_litigation_folder_id
    ):
        return
    # Auth / telemetry field-only saves must never block on Drive HTTP.
    if update_fields is not None:
        relevant = {
            "first_name",
            "last_name",
            "company_name",
            "status",
            "drive_folder_id",
            "drive_personal_documents_folder_id",
            "drive_litigation_folder_id",
            "drive_non_litigation_folder_id",
        }
        if not created and not (set(update_fields) & relevant):
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
    except (GoogleDriveAPIError, GoogleDriveOAuthError, OSError, TimeoutError) as exc:
        logger.warning(
            "Drive folder create skipped for client %s: %s", instance.pk, exc
        )


@receiver(post_save, sender=Employee)
def ensure_employee_drive_folders_on_save(
    sender, instance: Employee, created=False, update_fields=None, **kwargs
):
    """
    When an employee account exists and Drive is connected, ensure
    Employees/{Name}/Personal.

    Skips field-only auth updates (e.g. last_login) so login and live polls
    never wait on Google Drive under concurrent sessions.
    """
    if instance.drive_folder_id and instance.drive_personal_details_folder_id:
        return
    if update_fields is not None:
        relevant = {
            "first_name",
            "last_name",
            "status",
            "drive_folder_id",
            "drive_personal_details_folder_id",
        }
        if not created and not (set(update_fields) & relevant):
            return

    try:
        from .google_drive import (
            GoogleDriveAPIError,
            GoogleDriveOAuthError,
            GoogleDriveConnection,
            ensure_employee_folder_structure,
        )
    except Exception:
        return

    connection = GoogleDriveConnection.get_solo()
    if not connection.is_connected or not connection.work_folder_id:
        return

    try:
        ensure_employee_folder_structure(instance)
    except (GoogleDriveAPIError, GoogleDriveOAuthError, OSError, TimeoutError) as exc:
        logger.warning(
            "Drive folder create skipped for employee %s: %s", instance.pk, exc
        )
