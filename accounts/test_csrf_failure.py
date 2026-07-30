from django.test import Client, TestCase
from django.urls import reverse

from config.csrf import RETRY_MESSAGE


class CsrfFailureTests(TestCase):
    """A login page left open past its token should retry, not show a 403."""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.login_url = reverse("accounts:login")

    def post_with_stale_token(self, url, **extra):
        self.client.get(self.login_url)
        return self.client.post(
            url,
            {"csrfmiddlewaretoken": "stale", "username": "123456", "password": "x"},
            **extra,
        )

    def test_stale_login_token_redirects_back_to_the_form(self):
        response = self.post_with_stale_token(
            self.login_url,
            HTTP_REFERER=f"http://testserver{self.login_url}",
            follow=True,
        )

        self.assertEqual(response.redirect_chain, [(self.login_url, 302)])
        self.assertContains(response, RETRY_MESSAGE)

    def test_missing_referer_falls_back_to_the_login_page(self):
        response = self.post_with_stale_token(self.login_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.login_url)

    def test_offsite_referer_is_not_used_as_the_retry_target(self):
        response = self.post_with_stale_token(
            self.login_url, HTTP_REFERER="http://evil.example.com/login/"
        )

        self.assertEqual(response["Location"], self.login_url)

    def test_retry_response_carries_a_usable_token(self):
        self.post_with_stale_token(self.login_url)

        self.assertIn("csrftoken", self.client.cookies)

    def test_fetch_callers_get_json_instead_of_a_redirect(self):
        response = self.post_with_stale_token(
            self.login_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "csrf_expired")

    def test_header_token_callers_also_get_json(self):
        response = self.post_with_stale_token(
            self.login_url, HTTP_X_CSRFTOKEN="stale"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "csrf_expired")
