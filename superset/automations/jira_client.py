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


class JiraClient:
    """HTTP client for the Jira API.

    Attaches basic auth credentials sourced from the
    ``JIRA_API_EMAIL`` and ``JIRA_API_TOKEN`` environment variables.
    """

    def __init__(self) -> None:
        email = os.environ.get("JIRA_API_EMAIL", "")
        token = os.environ.get("JIRA_API_TOKEN", "")
        if not email or not token:
            raise ValueError(
                "JIRA_API_EMAIL and JIRA_API_TOKEN environment variables must be set"
            )
        self._session = requests.Session()
        self._session.auth = (email, token)
        self._session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        self._base_url = AutomationsConfig.JIRA_BASE_URL

    def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        assignee_name: str,
        label: str,
    ) -> dict[str, Any]:
        """Create a Jira bug ticket.

        Args:
            project_key: The Jira project key (e.g. ``SUP``).
            summary: Short summary / title for the issue.
            description: Full description in Atlassian Document Format.
            assignee_name: Display name of the assignee.
            label: Label to attach to the issue.

        Returns:
            The JSON response from the Jira API containing the created issue.

        Raises:
            requests.HTTPError: If the API returns a non-success status.
        """
        url = f"{self._base_url}/rest/api/3/issue"
        payload: dict[str, Any] = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": "Bug"},
                "assignee": {"displayName": assignee_name},
                "labels": [label],
                "description": {
                    "version": 1,
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": description,
                                }
                            ],
                        }
                    ],
                },
            }
        }
        response = self._session.post(url, json=payload)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result
