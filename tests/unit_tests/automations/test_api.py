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

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from superset.automations.config import AutomationsConfig
from superset.automations.devin_client import DevinClient
from superset.automations.jira_client import JiraClient
from superset.utils import json


def test_devin_client_requires_api_key() -> None:
    """DevinClient raises ValueError when DEVIN_API_KEY is missing."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="DEVIN_API_KEY"):
            DevinClient()


def test_devin_client_sets_auth_header() -> None:
    """DevinClient sets the Authorization Bearer header."""
    with patch.dict("os.environ", {"DEVIN_API_KEY": "test-key"}):
        client = DevinClient()
        assert client._session.headers["Authorization"] == "Bearer test-key"


def test_devin_client_build_prompt() -> None:
    """build_bug_identification_prompt returns expected prompt format."""
    with patch.dict("os.environ", {"DEVIN_API_KEY": "test-key"}):
        client = DevinClient()
        prompt = client.build_bug_identification_prompt(
            num_bugs=3, git_repo="owner/repo"
        )
        assert "3 bugs" in prompt
        assert "owner/repo" in prompt
        assert "erroneous code" in prompt
        assert "impact" in prompt
        assert "proposed fix" in prompt
        assert "bugs_report.json" in prompt


def test_devin_client_create_session() -> None:
    """create_session sends correct POST request."""
    with patch.dict("os.environ", {"DEVIN_API_KEY": "test-key"}):
        client = DevinClient()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "session_id": "sess-123",
            "bugs": [],
        }
        mock_response.raise_for_status = MagicMock()
        with patch.object(
            client._session, "post", return_value=mock_response
        ) as mock_post:
            result = client.create_session(org_id="org-456", prompt="find bugs")
            mock_post.assert_called_once_with(
                "https://api.devin.ai/v3/organizations/org-456/sessions",
                json={"prompt": "find bugs"},
            )
            assert result["session_id"] == "sess-123"


def test_jira_client_requires_credentials() -> None:
    """JiraClient raises ValueError when credentials are missing."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="JIRA_API_EMAIL"):
            JiraClient()


def test_jira_client_sets_basic_auth() -> None:
    """JiraClient sets basic auth with email and token."""
    with patch.dict(
        "os.environ",
        {"JIRA_API_EMAIL": "user@test.com", "JIRA_API_TOKEN": "jira-tok"},
    ):
        client = JiraClient()
        assert client._session.auth == ("user@test.com", "jira-tok")


def test_jira_client_create_issue() -> None:
    """create_issue sends correct POST request with proper payload."""
    with patch.dict(
        "os.environ",
        {"JIRA_API_EMAIL": "user@test.com", "JIRA_API_TOKEN": "jira-tok"},
    ):
        client = JiraClient()
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "10001", "key": "SUP-1"}
        mock_response.raise_for_status = MagicMock()
        with patch.object(
            client._session, "post", return_value=mock_response
        ) as mock_post:
            result = client.create_issue(
                project_key="SUP",
                summary="Test Bug",
                description="Bug description",
                assignee_account_id="abc123",
                label="!bug_fix_pr",
            )
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            payload = call_kwargs[1]["json"]
            assert payload["fields"]["project"]["key"] == "SUP"
            assert payload["fields"]["summary"] == "Test Bug"
            assert payload["fields"]["issuetype"]["name"] == "Bug"
            assert payload["fields"]["assignee"]["accountId"] == "abc123"
            assert payload["fields"]["labels"] == ["!bug_fix_pr"]
            assert result["key"] == "SUP-1"


def test_automations_config_defaults() -> None:
    """AutomationsConfig has expected default values."""
    with patch.dict("os.environ", {}, clear=True):
        config = AutomationsConfig()
        assert config.NUM_BUGS == 5
        assert config.DEVIN_API_BASE_URL == "https://api.devin.ai"
        assert config.JIRA_BASE_URL == "https://gabrielaasuncion.atlassian.net"
        assert config.JIRA_ASSIGNEE_NAME == "Devin Bug Hunter"
        assert config.JIRA_BUG_LABEL == "!bug_fix_pr"
        assert config.TARGET_GIT_REPO == "gabbyasuncion/superset"


def test_automations_config_from_env() -> None:
    """AutomationsConfig reads values from environment variables."""
    with patch.dict(
        "os.environ",
        {
            "AUTOMATIONS_NUM_BUGS": "10",
            "DEVIN_ORG_ID": "org-test",
            "JIRA_PROJECT_KEY": "TEST",
        },
    ):
        config = AutomationsConfig()
        assert config.NUM_BUGS == 10
        assert config.DEVIN_ORG_ID == "org-test"
        assert config.JIRA_PROJECT_KEY == "TEST"


def test_tickets_endpoint_requires_auth(client: Any) -> None:
    """POST /api/v1/automations/tickets requires authentication."""
    response = client.post("/api/v1/automations/tickets")
    assert response.status_code == 401


def test_tickets_endpoint_missing_org_id(client: Any, full_api_access: None) -> None:
    """POST /api/v1/automations/tickets returns 400 when DEVIN_ORG_ID is missing."""
    with patch.dict("os.environ", {"DEVIN_API_KEY": "key", "DEVIN_ORG_ID": ""}):
        response = client.post("/api/v1/automations/tickets")
        assert response.status_code == 400


def test_tickets_endpoint_success(client: Any, full_api_access: None) -> None:
    """POST /api/v1/automations/tickets creates tickets successfully."""
    env_vars = {
        "DEVIN_API_KEY": "test-key",
        "DEVIN_ORG_ID": "org-123",
        "JIRA_API_EMAIL": "user@test.com",
        "JIRA_API_TOKEN": "jira-tok",
        "AUTOMATIONS_NUM_BUGS": "2",
    }

    bugs_data = [
        {
            "title": "Bug 1",
            "erroneous_code": "bad code 1",
            "impact": "high impact",
            "proposed_fix": "fix it",
        },
        {
            "title": "Bug 2",
            "erroneous_code": "bad code 2",
            "impact": "low impact",
            "proposed_fix": "patch it",
        },
    ]
    bugs_json = json.dumps(bugs_data)

    create_session_response = {"session_id": "sess-abc", "status": "running"}
    messages_response = [
        {"role": "assistant", "text": "I found 2 bugs."},
    ]
    attachments_response = [
        {
            "attachment_id": "att_1",
            "name": "bugs_report.json",
            "url": "https://example.com/bugs_report.json",
        },
    ]

    jira_responses = [
        {"id": "10001", "key": "SUP-1"},
        {"id": "10002", "key": "SUP-2"},
    ]

    mock_devin = MagicMock()
    mock_devin.build_bug_identification_prompt.return_value = "find bugs"
    mock_devin.create_session.return_value = create_session_response
    mock_devin.poll_for_devin_message.return_value = messages_response
    mock_devin.list_attachments.return_value = attachments_response
    mock_devin.download_attachment.return_value = bugs_json

    mock_jira = MagicMock()
    mock_jira.create_issue.side_effect = jira_responses

    with patch.dict("os.environ", env_vars):
        with (
            patch(
                "superset.automations.api.AutomationsRestApi.devin_client",
                new_callable=lambda: property(lambda self: mock_devin),
            ),
            patch(
                "superset.automations.api.AutomationsRestApi.jira_client",
                new_callable=lambda: property(lambda self: mock_jira),
            ),
        ):
            response = client.post("/api/v1/automations/tickets")
            assert response.status_code == 200
            data = response.json
            assert data["session_id"] == "sess-abc"
            assert data["bugs_requested"] == 2
            assert len(data["tickets_created"]) == 2
            assert mock_jira.create_issue.call_count == 2
            mock_devin.poll_for_devin_message.assert_called_once()
            mock_devin.list_attachments.assert_called_once()
            mock_devin.download_attachment.assert_called_once_with(
                "att_1", "bugs_report.json"
            )


def test_tickets_endpoint_timeout(client: Any, full_api_access: None) -> None:
    """POST /api/v1/automations/tickets returns 500 on message polling timeout."""
    env_vars = {
        "DEVIN_API_KEY": "test-key",
        "DEVIN_ORG_ID": "org-123",
        "JIRA_API_EMAIL": "user@test.com",
        "JIRA_API_TOKEN": "jira-tok",
    }

    mock_devin = MagicMock()
    mock_devin.build_bug_identification_prompt.return_value = "find bugs"
    mock_devin.create_session.return_value = {
        "session_id": "sess-timeout",
        "status": "running",
    }
    mock_devin.poll_for_devin_message.side_effect = TimeoutError(
        "Devin session sess-timeout did not respond within 1800s"
    )

    with patch.dict("os.environ", env_vars):
        with patch(
            "superset.automations.api.AutomationsRestApi.devin_client",
            new_callable=lambda: property(lambda self: mock_devin),
        ):
            response = client.post("/api/v1/automations/tickets")
            assert response.status_code == 500


def test_tickets_endpoint_missing_attachment(
    client: Any, full_api_access: None
) -> None:
    """POST /api/v1/automations/tickets returns 400 when bugs_report.json missing."""
    env_vars = {
        "DEVIN_API_KEY": "test-key",
        "DEVIN_ORG_ID": "org-123",
        "JIRA_API_EMAIL": "user@test.com",
        "JIRA_API_TOKEN": "jira-tok",
    }

    mock_devin = MagicMock()
    mock_devin.build_bug_identification_prompt.return_value = "find bugs"
    mock_devin.create_session.return_value = {
        "session_id": "sess-no-file",
        "status": "running",
    }
    mock_devin.poll_for_devin_message.return_value = [
        {"role": "assistant", "text": "Done"},
    ]
    mock_devin.list_attachments.return_value = [
        {"attachment_id": "att_1", "name": "other_file.txt", "url": "https://x.com/f"},
    ]

    with patch.dict("os.environ", env_vars):
        with patch(
            "superset.automations.api.AutomationsRestApi.devin_client",
            new_callable=lambda: property(lambda self: mock_devin),
        ):
            response = client.post("/api/v1/automations/tickets")
            assert response.status_code == 400


def test_download_bugs_report() -> None:
    """_download_bugs_report finds and downloads bugs_report.json."""
    from superset.automations.api import AutomationsRestApi

    bugs_data = [
        {
            "title": "NPE in foo",
            "erroneous_code": "x.bar()",
            "impact": "crash",
            "proposed_fix": "null check",
        }
    ]

    api = AutomationsRestApi.__new__(AutomationsRestApi)
    mock_devin = MagicMock()
    mock_devin.download_attachment.return_value = json.dumps(bugs_data)

    with patch(
        "superset.automations.api.AutomationsRestApi.devin_client",
        new_callable=lambda: property(lambda self: mock_devin),
    ):
        attachments = [
            {
                "attachment_id": "att_1",
                "name": "bugs_report.json",
                "url": "https://example.com/bugs.json",
            },
        ]
        result = api._download_bugs_report(attachments)
        mock_devin.download_attachment.assert_called_once_with(
            "att_1", "bugs_report.json"
        )
        assert len(result) == 1
        assert result[0]["title"] == "NPE in foo"


def test_download_bugs_report_not_found() -> None:
    """_download_bugs_report raises ValueError when file not found."""
    from superset.automations.api import AutomationsRestApi

    api = AutomationsRestApi.__new__(AutomationsRestApi)
    attachments = [
        {"attachment_id": "att_1", "name": "other.txt", "url": "https://x.com/f"},
    ]
    with pytest.raises(ValueError, match="bugs_report.json not found"):
        api._download_bugs_report(attachments)  # no org_id needed
