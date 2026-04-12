# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from superset.automations.config import AutomationsConfig

logger = logging.getLogger(__name__)


class DevinClient:
    """HTTP client for the Devin API.

    Attaches an Authorization Bearer header sourced from the
    ``DEVIN_API_KEY`` environment variable.
    """

    # Retry configuration for 429 rate-limit responses
    _MAX_RETRIES: int = 5
    _INITIAL_BACKOFF: float = 2.0
    _BACKOFF_FACTOR: float = 2.0
    _MAX_BACKOFF: float = 120.0

    def __init__(self) -> None:
        api_key = os.environ.get("DEVIN_API_KEY", "")
        if not api_key:
            raise ValueError("DEVIN_API_KEY environment variable is not set")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )
        self._base_url = AutomationsConfig.DEVIN_API_BASE_URL

    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        """Execute an HTTP request with exponential backoff on 429 responses.

        Respects the ``Retry-After`` header when present. Falls back to
        exponential backoff starting at :pyattr:`_INITIAL_BACKOFF` seconds,
        doubling each attempt up to :pyattr:`_MAX_BACKOFF`.

        Args:
            method: HTTP method (``GET``, ``POST``, etc.).
            url: The request URL.
            **kwargs: Additional keyword arguments forwarded to
                ``requests.Session.request``.

        Returns:
            The successful :class:`requests.Response`.

        Raises:
            requests.HTTPError: If a non-429 error occurs, or if retries
                are exhausted.
        """
        backoff = self._INITIAL_BACKOFF
        for attempt in range(self._MAX_RETRIES + 1):
            response = self._session.request(method, url, **kwargs)
            if response.status_code != 429:
                return response

            if attempt == self._MAX_RETRIES:
                logger.error(
                    "Devin API rate limit exceeded after %d retries: "
                    "status=%s url=%s body=%s",
                    self._MAX_RETRIES,
                    response.status_code,
                    url,
                    response.text,
                )
                response.raise_for_status()

            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    wait_time = float(retry_after)
                except ValueError:
                    wait_time = backoff
            else:
                wait_time = backoff

            logger.warning(
                "Devin API returned 429, retrying in %.1fs (attempt %d/%d, url=%s)",
                wait_time,
                attempt + 1,
                self._MAX_RETRIES,
                url,
            )
            time.sleep(wait_time)
            backoff = min(backoff * self._BACKOFF_FACTOR, self._MAX_BACKOFF)

        # Should not be reached, but satisfies type checker
        response.raise_for_status()  # pragma: no cover
        return response  # pragma: no cover

    def create_session(
        self,
        org_id: str,
        prompt: str,
    ) -> dict[str, Any]:
        """Create a Devin session to identify bugs.

        Sends a POST request to
        ``/v3/organizations/{org_id}/sessions`` with the given prompt.

        Args:
            org_id: The Devin organization ID.
            prompt: The prompt describing what bugs to find.

        Returns:
            The JSON response from the Devin API.

        Raises:
            requests.HTTPError: If the API returns a non-success status.
        """
        url = f"{self._base_url}/v3/organizations/{org_id}/sessions"
        payload: dict[str, Any] = {"prompt": prompt}
        response = self._request_with_retry("POST", url, json=payload)
        if not response.ok:
            logger.error(
                "Devin API request failed: status=%s url=%s body=%s",
                response.status_code,
                url,
                response.text,
            )
            response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    def get_session(
        self,
        org_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        """Get the current status of a Devin session.

        Args:
            org_id: The Devin organization ID.
            session_id: The Devin session ID.

        Returns:
            The JSON response containing session status and metadata.

        Raises:
            requests.HTTPError: If the API returns a non-success status.
        """
        url = f"{self._base_url}/v3/organizations/{org_id}/sessions/{session_id}"
        response = self._request_with_retry("GET", url)
        if not response.ok:
            logger.error(
                "Devin API get session failed: status=%s url=%s body=%s",
                response.status_code,
                url,
                response.text,
            )
            response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    def list_messages(
        self,
        org_id: str,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """List all messages for a Devin session.

        Uses cursor-based pagination to retrieve all messages.

        Args:
            org_id: The Devin organization ID.
            session_id: The Devin session ID.

        Returns:
            A list of message objects from the session.

        Raises:
            requests.HTTPError: If the API returns a non-success status.
        """
        url = (
            f"{self._base_url}/v3/organizations/{org_id}/sessions/{session_id}/messages"
        )
        all_messages: list[dict[str, Any]] = []
        params: dict[str, Any] = {"first": 200}

        while True:
            response = self._request_with_retry("GET", url, params=params)
            if not response.ok:
                logger.error(
                    "Devin API list messages failed: status=%s url=%s body=%s",
                    response.status_code,
                    url,
                    response.text,
                )
                response.raise_for_status()
            data = response.json()
            items = data.get("items", [])
            all_messages.extend(items)

            page_info = data.get("page_info", {})
            if not page_info.get("has_next_page", False):
                break
            params["after"] = page_info["end_cursor"]

        return all_messages

    def list_attachments(
        self,
        org_id: str,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """List all attachments for a Devin session.

        Args:
            org_id: The Devin organization ID.
            session_id: The Devin session ID.

        Returns:
            A list of attachment objects, each with ``attachment_id``,
            ``name``, and ``url`` keys.

        Raises:
            requests.HTTPError: If the API returns a non-success status.
        """
        url = (
            f"{self._base_url}/v3/organizations/{org_id}"
            f"/sessions/{session_id}/attachments"
        )
        response = self._request_with_retry("GET", url)
        if not response.ok:
            logger.error(
                "Devin API list attachments failed: status=%s url=%s body=%s",
                response.status_code,
                url,
                response.text,
            )
            response.raise_for_status()
        data = response.json()
        # The attachments endpoint returns a JSON array directly.
        if isinstance(data, list):
            return data
        # Fallback: if the response is wrapped in an object, try "items".
        items: list[dict[str, Any]] = data.get("items", [])
        return items

    def download_attachment(
        self,
        org_id: str,
        attachment_id: str,
        attachment_name: str,
    ) -> str:
        """Download an attachment and return the content as text.

        Sends a GET request to
        ``/v3/organizations/{org_id}/attachments/{uuid}/{name}``.
        The endpoint returns a 307 redirect to a presigned URL that
        provides temporary access to the file.

        Args:
            org_id: The Devin organization ID.
            attachment_id: The unique identifier (UUID) of the attachment.
            attachment_name: The filename of the attachment.

        Returns:
            The text content of the downloaded file.

        Raises:
            requests.HTTPError: If the download fails.
        """
        url = (
            f"{self._base_url}/v3/organizations/{org_id}"
            f"/attachments/{attachment_id}/{attachment_name}"
        )
        response = self._request_with_retry("GET", url, allow_redirects=True)
        if not response.ok:
            logger.error(
                "Devin API download attachment failed: status=%s url=%s body=%s",
                response.status_code,
                url,
                response.text,
            )
            response.raise_for_status()
        return response.text

    def poll_for_devin_message(
        self,
        org_id: str,
        session_id: str,
        poll_interval: int = 30,
        timeout: int = 1800,
    ) -> dict[str, Any]:
        """Poll session attachments until bugs_report.json is available.

        Checks for a ``bugs_report.json`` attachment by polling the attachments
        endpoint at the configured interval.

        Args:
            org_id: The Devin organization ID.
            session_id: The Devin session ID.
            poll_interval: Seconds between attachment checks.
            timeout: Maximum seconds to wait before raising TimeoutError.

        Returns:
            The attachment object for ``bugs_report.json``.

        Raises:
            TimeoutError: If ``bugs_report.json`` does not appear within timeout.
            requests.HTTPError: If any API call fails.
        """
        elapsed = 0
        while elapsed < timeout:
            attachments = self.list_attachments(org_id, session_id)
            bugs_report = next(
                (a for a in attachments if a.get("name") == "bugs_report.json"),
                None,
            )
            if bugs_report:
                logger.info(
                    "Devin session %s: bugs_report.json found (elapsed: %ds)",
                    session_id,
                    elapsed,
                )
                return bugs_report
            logger.info(
                "Devin session %s: bugs_report.json not yet available (elapsed: %ds)",
                session_id,
                elapsed,
            )
            time.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(
            f"Devin session {session_id} did not produce "
            f"bugs_report.json within {timeout}s"
        )

    def build_bug_identification_prompt(
        self,
        num_bugs: int,
        git_repo: str,
    ) -> str:
        """Build a prompt for Devin to identify bugs in a repository.

        Args:
            num_bugs: The number of bugs to identify.
            git_repo: The Git repository path (e.g. ``owner/repo``).

        Returns:
            A prompt string for the Devin API.
        """
        return (
            f"Identify {num_bugs} bugs in the {git_repo} Git repository. "
            f"For each bug, provide:\n"
            f"1. A description of the erroneous code\n"
            f"2. Its impact on the application\n"
            f"3. A proposed fix\n\n"
            f"Output the results as a JSON file named bugs_report.json "
            f"containing a JSON array where each element has "
            f"the keys: 'title', 'erroneous_code', 'impact', 'proposed_fix'."
        )
