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

from superset.automations.api import AutomationsRestApi
from superset.automations.config import AutomationsConfig
from superset.automations.devin_client import DevinClient
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
        assert "description" in prompt
        assert "application_impact" in prompt
        assert "severity_level" in prompt
        assert "Devin's Bugs Report: " in prompt


def test_devin_client_create_session() -> None:
    """create_session sends correct POST request."""
    with patch.dict("os.environ", {"DEVIN_API_KEY": "test-key"}):
        client = DevinClient()
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "session_id": "sess-123",
            "bugs": [],
        }
        mock_response.status_code = 200
        with patch.object(
            client._session, "request", return_value=mock_response
        ) as mock_request:
            result = client.create_session(org_id="org-456", prompt="find bugs")
            mock_request.assert_called_once_with(
                "POST",
                "https://api.devin.ai/v3/organizations/org-456/sessions",
                json={"prompt": "find bugs"},
            )
            assert result["session_id"] == "sess-123"


def test_devin_client_send_message() -> None:
    """send_message sends correct POST request."""
    with patch.dict("os.environ", {"DEVIN_API_KEY": "test-key"}):
        client = DevinClient()
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"status": "ok"}
        mock_response.status_code = 200
        with patch.object(
            client._session, "request", return_value=mock_response
        ) as mock_request:
            result = client.send_message(
                org_id="org-456",
                session_id="sess-123",
                message="Please open a PR",
            )
            mock_request.assert_called_once_with(
                "POST",
                "https://api.devin.ai/v3/organizations/org-456"
                "/sessions/devin-sess-123/messages",
                json={"message": "Please open a PR"},
            )
            assert result["status"] == "ok"


def test_devin_client_send_message_with_prefix() -> None:
    """send_message does not double-prefix devin- IDs."""
    with patch.dict("os.environ", {"DEVIN_API_KEY": "test-key"}):
        client = DevinClient()
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"status": "ok"}
        mock_response.status_code = 200
        with patch.object(
            client._session, "request", return_value=mock_response
        ) as mock_request:
            client.send_message(
                org_id="org-456",
                session_id="devin-sess-123",
                message="Please open a PR",
            )
            mock_request.assert_called_once_with(
                "POST",
                "https://api.devin.ai/v3/organizations/org-456"
                "/sessions/devin-sess-123/messages",
                json={"message": "Please open a PR"},
            )


def test_automations_config_defaults() -> None:
    """AutomationsConfig has expected default values."""
    with patch.dict("os.environ", {}, clear=True):
        config = AutomationsConfig()
        assert config.NUM_BUGS == 3
        assert config.DEVIN_API_BASE_URL == "https://api.devin.ai"
        assert config.TARGET_GIT_REPO == "gabbyasuncion/superset"


def test_automations_config_from_env() -> None:
    """AutomationsConfig reads values from environment variables."""
    with patch.dict(
        "os.environ",
        {
            "AUTOMATIONS_NUM_BUGS": "10",
            "DEVIN_ORG_ID": "org-test",
        },
    ):
        config = AutomationsConfig()
        assert config.NUM_BUGS == 10
        assert config.DEVIN_ORG_ID == "org-test"


def test_bug_swatter_endpoint_requires_auth(client: Any) -> None:
    """POST /api/v1/automations/bug_swatter requires authentication."""
    response = client.post("/api/v1/automations/bug_swatter")
    assert response.status_code == 401


def test_bug_swatter_endpoint_missing_org_id(
    client: Any, full_api_access: None
) -> None:
    """POST /api/v1/automations/bug_swatter returns 400 when DEVIN_ORG_ID is missing."""
    with patch.dict("os.environ", {"DEVIN_API_KEY": "key", "DEVIN_ORG_ID": ""}):
        response = client.post("/api/v1/automations/bug_swatter")
        assert response.status_code == 400


def test_bug_swatter_endpoint_success(client: Any, full_api_access: None) -> None:
    """POST /api/v1/automations/bug_swatter sends PR prompts successfully."""
    env_vars = {
        "DEVIN_API_KEY": "test-key",
        "DEVIN_ORG_ID": "org-123",
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
    bugs_message = f"Devin's Bugs Report: {bugs_json}"

    create_session_response = {"session_id": "sess-abc", "status": "running"}

    send_message_response = {"status": "ok"}

    mock_devin = MagicMock()
    mock_devin.build_bug_identification_prompt.return_value = "find bugs"
    mock_devin.create_session.return_value = create_session_response
    mock_devin.poll_for_devin_message.return_value = bugs_message
    mock_devin.send_message.return_value = send_message_response

    with patch.dict("os.environ", env_vars):
        with patch.object(
            AutomationsRestApi,
            "_get_devin_client",
            return_value=mock_devin,
        ):
            response = client.post("/api/v1/automations/bug_swatter")
            assert response.status_code == 200
            data = response.json
            assert data["session_id"] == "sess-abc"
            assert data["bugs_requested"] == 2
            assert len(data["bugs_found"]) == 2
            mock_devin.poll_for_devin_message.assert_called_once()


def test_bug_swatter_endpoint_timeout(client: Any, full_api_access: None) -> None:
    """POST /api/v1/automations/bug_swatter returns 500 on message polling timeout."""
    env_vars = {
        "DEVIN_API_KEY": "test-key",
        "DEVIN_ORG_ID": "org-123",
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
        with patch.object(
            AutomationsRestApi,
            "_get_devin_client",
            return_value=mock_devin,
        ):
            response = client.post("/api/v1/automations/bug_swatter")
            assert response.status_code == 500


def test_bug_swatter_endpoint_bad_message(client: Any, full_api_access: None) -> None:
    """POST /bug_swatter returns 400 when message has wrong prefix."""
    env_vars = {
        "DEVIN_API_KEY": "test-key",
        "DEVIN_ORG_ID": "org-123",
    }

    mock_devin = MagicMock()
    mock_devin.build_bug_identification_prompt.return_value = "find bugs"
    mock_devin.create_session.return_value = {
        "session_id": "sess-bad-msg",
        "status": "running",
    }
    mock_devin.poll_for_devin_message.return_value = "No prefix here"

    with patch.dict("os.environ", env_vars):
        with patch.object(
            AutomationsRestApi,
            "_get_devin_client",
            return_value=mock_devin,
        ):
            response = client.post("/api/v1/automations/bug_swatter")
            assert response.status_code == 400


def test_parse_bugs_from_message() -> None:
    """_parse_bugs_from_message extracts bugs JSON from prefixed message."""
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
    message_text = f"Devin's Bugs Report: {json.dumps(bugs_data)}"
    result = api._parse_bugs_from_message(message_text)
    assert len(result) == 1
    assert result[0]["title"] == "NPE in foo"


def test_parse_bugs_from_message_bad_prefix() -> None:
    """_parse_bugs_from_message raises ValueError when prefix is missing."""
    from superset.automations.api import AutomationsRestApi

    api = AutomationsRestApi.__new__(AutomationsRestApi)
    with pytest.raises(ValueError, match="does not start with expected prefix"):
        api._parse_bugs_from_message("No prefix here []")
