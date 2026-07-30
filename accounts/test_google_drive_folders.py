from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from accounts.google_drive import ensure_folder


class EnsureDriveFolderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("accounts.google_drive.create_folder")
    @patch("accounts.google_drive.find_child_folder_by_name")
    @patch("accounts.google_drive._fetch_folder_state")
    def test_replaces_stored_folder_outside_expected_parent(
        self, fetch_state, find_child, create_folder
    ):
        fetch_state.return_value = {
            "id": "stale-category",
            "name": "Letters",
            "parents": ["wrong-parent"],
        }
        find_child.return_value = "correct-category"

        folder_id = ensure_folder(
            "token",
            name="Letters",
            parent_id="templates-folder",
            existing_id="stale-category",
        )

        self.assertEqual(folder_id, "correct-category")
        find_child.assert_called_once_with(
            "token", "templates-folder", "Letters"
        )
        create_folder.assert_not_called()

    @patch("accounts.google_drive.find_child_folder_by_name")
    @patch("accounts.google_drive._fetch_folder_state")
    def test_keeps_stored_folder_inside_expected_parent(
        self, fetch_state, find_child
    ):
        fetch_state.return_value = {
            "id": "category-folder",
            "name": "Letters",
            "parents": ["templates-folder"],
        }

        folder_id = ensure_folder(
            "token",
            name="Letters",
            parent_id="templates-folder",
            existing_id="category-folder",
        )

        self.assertEqual(folder_id, "category-folder")
        find_child.assert_not_called()
