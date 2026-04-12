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
from typing import Any

from flask import Response
from flask_appbuilder import expose
from flask_appbuilder.security.decorators import permission_name, protect

from superset.automations.config import AutomationsConfig
from superset.automations.devin_client import DevinClient
from superset.automations.jira_client import JiraClient
from superset.automations.schemas import AutomationsTicketsResponseSchema
from superset.extensions import event_logger
from superset.utils import json
from superset.views.base_api import BaseSupersetApi, statsd_metrics

logger = logging.getLogger(__name__)


class AutomationsRestApi(BaseSupersetApi):
    """Automations Admin API.

    Provides endpoints for automated workflows such as identifying bugs
    via the Devin API and filing Jira tickets. Access is restricted to
    authorized internal users via JWT tokens minted by the
    ``/api/v1/security/login`` endpoint.

    The Devin and Jira HTTP clients are initialized once and reused
    across requests and endpoints via :pyattr:`devin_client` and
    :pyattr:`jira_client`.
    """

    resource_name = "automations"
    allow_browser_login = False
    openapi_spec_tag = "Automations"
    openapi_spec_component_schemas = (AutomationsTicketsResponseSchema,)

    _devin_client: DevinClient | None = None
    _jira_client: JiraClient | None = None

    @property
    def devin_client(self) -> DevinClient:
        """Return a reusable Devin API client, creating one if needed."""
        if self._devin_client is None:
            self.__class__._devin_client = DevinClient()
        return self._devin_client  # type: ignore[return-value]

    @property
    def jira_client(self) -> JiraClient:
        """Return a reusable Jira API client, creating one if needed."""
        if self._jira_client is None:
            self.__class__._jira_client = JiraClient()
        return self._jira_client  # type: ignore[return-value]

    @expose("/tickets", methods=("POST",))
    @event_logger.log_this
    @protect()
    @statsd_metrics
    @permission_name("create_tickets")
    def tickets(self) -> Response:
        """Identify bugs via Devin and file Jira tickets.
        ---
        post:
          summary: Identify bugs and create Jira tickets
          description: >-
            Uses the Devin API to identify bugs in the superset
            repository and creates Jira bug tickets for each bug found.
            The number of bugs to identify is sourced from the
            automations configuration.
          responses:
            200:
              description: Tickets created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      session_id:
                        type: string
                      tickets_created:
                        type: array
                        items:
                          type: object
                      bugs_requested:
                        type: integer
            400:
              $ref: '#/components/responses/400'
            401:
              $ref: '#/components/responses/401'
            500:
              $ref: '#/components/responses/500'
        """
        try:
            config = AutomationsConfig()
            num_bugs = config.NUM_BUGS
            org_id = config.DEVIN_ORG_ID
            git_repo = config.TARGET_GIT_REPO

            if not org_id:
                return self.response_400(message="DEVIN_ORG_ID is not configured")

            # Step 1: Create a Devin session to identify bugs
            prompt = self.devin_client.build_bug_identification_prompt(
                num_bugs=num_bugs,
                git_repo=git_repo,
            )
            # devin_response = self.devin_client.create_session(
            #     org_id=org_id,
            #     prompt=prompt,
            # )

            session_id = "195c529a1bc84d5cae2f5c74cafdbd9d"
            if not session_id:
                return self.response_500(
                    message="Devin API did not return a session_id"
                )

            # Step 2: Poll messages until Devin responds
            logger.info("Polling Devin session %s for a response message", session_id)
            self.devin_client.poll_for_devin_message(
                org_id=org_id,
                session_id=session_id,
                poll_interval=config.DEVIN_POLL_INTERVAL,
                timeout=config.DEVIN_POLL_TIMEOUT,
            )

            # Step 3: Retrieve bugs_report.json from session attachments
            attachments = self.devin_client.list_attachments(
                org_id=org_id,
                session_id=session_id,
            )

            bugs = self._download_bugs_report(attachments, org_id=org_id)
            logger.info(
                "Extracted %d bugs from Devin session %s", len(bugs), session_id
            )

            # Step 4: Create Jira tickets for each bug
            tickets_created: list[dict[str, Any]] = []

            for bug in bugs:
                title = bug.get("title", "Bug identified by Devin")
                erroneous_code = bug.get("erroneous_code", "")
                impact = bug.get("impact", "")
                proposed_fix = bug.get("proposed_fix", "")

                description = (
                    f"Erroneous Code:\n{erroneous_code}\n\n"
                    f"Impact:\n{impact}\n\n"
                    f"Proposed Fix:\n{proposed_fix}"
                )

                ticket = self.jira_client.create_issue(
                    project_key=config.JIRA_PROJECT_KEY,
                    summary=title,
                    description=description,
                    assignee_account_id=config.JIRA_ASSIGNEE_ACCOUNT_ID,
                    label=config.JIRA_BUG_LABEL,
                )
                tickets_created.append(ticket)

            return self.response(
                200,
                session_id=session_id,
                tickets_created=tickets_created,
                bugs_requested=num_bugs,
            )

        except TimeoutError as ex:
            logger.error("Devin session polling timed out: %s", ex)
            return self.response_500(message=str(ex))
        except ValueError as ex:
            logger.error("Configuration error: %s", ex)
            return self.response_400(message=str(ex))
        except Exception as ex:
            logger.exception("Failed to create automation tickets")
            return self.response_500(message=str(ex))

    _BUGS_REPORT_FILENAME: str = "bugs_report.json"

    def _download_bugs_report(
        self,
        attachments: list[dict[str, Any]],
        org_id: str,
    ) -> list[dict[str, Any]]:
        """Find and download bugs_report.json from session attachments.

        Args:
            attachments: List of attachment dicts from the Devin API.

        Returns:
            A list of bug dicts parsed from the attachment content.

        Raises:
            ValueError: If ``bugs_report.json`` is not found among
                the attachments.
        """
        for attachment in attachments:
            if attachment.get("name") == self._BUGS_REPORT_FILENAME:
                attachment_id = attachment.get("attachment_id", "")
                attachment_name = attachment.get("attachment_name", "")
                content = self.devin_client.download_attachment(org_id, attachment_id, attachment_name)
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    return parsed  # type: ignore[no-any-return]
                logger.warning(
                    "%s content is not a JSON array", self._BUGS_REPORT_FILENAME
                )
                return []

        raise ValueError(
            f"{self._BUGS_REPORT_FILENAME} not found in session attachments"
        )
