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
from typing import Any

import requests

from superset.automations.config import AutomationsConfig

logger = logging.getLogger(__name__)


class DevinClient:
    """HTTP client for the Devin API.

    Attaches an Authorization Bearer header sourced from the
    ``DEVIN_API_KEY`` environment variable.
    """

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
        response = self._session.post(url, json=payload)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

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
            f"Return the results as a JSON array where each element has "
            f"the keys: 'title', 'erroneous_code', 'impact', 'proposed_fix'."
        )
