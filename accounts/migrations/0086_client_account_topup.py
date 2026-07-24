from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def _column_names(schema_editor, table):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM {table}")
        return {row[0] for row in cursor.fetchall()}


def _table_exists(schema_editor, table):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SHOW TABLES LIKE %s", [table])
        return cursor.fetchone() is not None


def apply_client_topup_schema(apps, schema_editor):
    Client = apps.get_model("accounts", "Client")
    MpesaStkRequest = apps.get_model("accounts", "MpesaStkRequest")
    client_table = Client._meta.db_table
    stk_table = MpesaStkRequest._meta.db_table
    topup_table = "accounts_clientaccounttopup"

    client_cols = _column_names(schema_editor, client_table)
    if "credit_balance" not in client_cols:
        schema_editor.execute(
            f"ALTER TABLE {client_table} "
            "ADD COLUMN credit_balance decimal(14,2) NOT NULL DEFAULT 0.00"
        )

    stk_cols = _column_names(schema_editor, stk_table)
    if "client_id" not in stk_cols:
        schema_editor.execute(
            f"ALTER TABLE {stk_table} "
            "ADD COLUMN client_id bigint NULL, "
            "ADD CONSTRAINT accounts_mpesastkrequest_client_id_fk "
            f"FOREIGN KEY (client_id) REFERENCES {client_table}(id) "
            "ON DELETE CASCADE"
        )
    if "purpose" not in stk_cols:
        schema_editor.execute(
            f"ALTER TABLE {stk_table} "
            "ADD COLUMN purpose varchar(32) NOT NULL DEFAULT 'invoice_payment'"
        )

    # Make invoice_id nullable if needed
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM {stk_table} LIKE 'invoice_id'")
        invoice_col = cursor.fetchone()
    if invoice_col and invoice_col[2] == "NO":
        schema_editor.execute(
            f"ALTER TABLE {stk_table} MODIFY invoice_id bigint NULL"
        )

    if not _table_exists(schema_editor, topup_table):
        schema_editor.execute(
            f"""
            CREATE TABLE {topup_table} (
                id bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
                amount decimal(14,2) NOT NULL,
                method varchar(16) NOT NULL,
                status varchar(16) NOT NULL,
                note longtext NOT NULL,
                phone varchar(20) NOT NULL,
                mpesa_receipt varchar(64) NOT NULL,
                balance_after decimal(14,2) NULL,
                created_at datetime(6) NOT NULL,
                updated_at datetime(6) NOT NULL,
                client_id bigint NOT NULL,
                created_by_id bigint NULL,
                stk_request_id bigint NULL UNIQUE,
                CONSTRAINT accounts_clientaccounttopup_client_id_fk
                    FOREIGN KEY (client_id) REFERENCES {client_table}(id)
                    ON DELETE CASCADE,
                CONSTRAINT accounts_clientaccounttopup_created_by_id_fk
                    FOREIGN KEY (created_by_id) REFERENCES accounts_employee(id)
                    ON DELETE SET NULL,
                CONSTRAINT accounts_clientaccounttopup_stk_request_id_fk
                    FOREIGN KEY (stk_request_id) REFERENCES {stk_table}(id)
                    ON DELETE SET NULL
            )
            """
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0085_companyaccounttopup_source_type"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="client",
                    name="credit_balance",
                    field=models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Prepaid credit available on this client account.",
                        max_digits=14,
                        verbose_name="Account credit balance",
                    ),
                ),
                migrations.AlterField(
                    model_name="mpesastkrequest",
                    name="invoice",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stk_requests",
                        to="accounts.invoice",
                    ),
                ),
                migrations.AddField(
                    model_name="mpesastkrequest",
                    name="client",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stk_requests",
                        to="accounts.client",
                    ),
                ),
                migrations.AddField(
                    model_name="mpesastkrequest",
                    name="purpose",
                    field=models.CharField(
                        choices=[
                            ("invoice_payment", "Invoice payment"),
                            ("client_topup", "Client account top-up"),
                        ],
                        default="invoice_payment",
                        max_length=32,
                    ),
                ),
                migrations.CreateModel(
                    name="ClientAccountTopup",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "amount",
                            models.DecimalField(decimal_places=2, max_digits=14),
                        ),
                        (
                            "method",
                            models.CharField(
                                choices=[
                                    ("manual", "Manual"),
                                    ("mpesa", "M-Pesa"),
                                ],
                                max_length=16,
                            ),
                        ),
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("pending", "Pending"),
                                    ("completed", "Completed"),
                                    ("failed", "Failed"),
                                ],
                                default="completed",
                                max_length=16,
                            ),
                        ),
                        ("note", models.TextField(blank=True, default="")),
                        (
                            "phone",
                            models.CharField(blank=True, default="", max_length=20),
                        ),
                        (
                            "mpesa_receipt",
                            models.CharField(blank=True, default="", max_length=64),
                        ),
                        (
                            "balance_after",
                            models.DecimalField(
                                blank=True,
                                decimal_places=2,
                                max_digits=14,
                                null=True,
                            ),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "client",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="account_topups",
                                to="accounts.client",
                            ),
                        ),
                        (
                            "created_by",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="client_account_topups_created",
                                to="accounts.employee",
                            ),
                        ),
                        (
                            "stk_request",
                            models.OneToOneField(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="client_topup",
                                to="accounts.mpesastkrequest",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Client account top-up",
                        "verbose_name_plural": "Client account top-ups",
                        "ordering": ["-created_at", "-id"],
                    },
                ),
            ],
            database_operations=[
                migrations.RunPython(apply_client_topup_schema, noop_reverse),
            ],
        ),
    ]
