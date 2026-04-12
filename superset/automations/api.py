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

import os

from flask import current_app, request, Response
from jinja2 import Environment, FileSystemLoader
from flask_appbuilder import expose
from flask_appbuilder.security.decorators import permission_name, protect

from superset.automations.config import AutomationsConfig
from superset.automations.devin_client import DevinClient, PRMetrics
from superset.automations.jira_client import JiraClient
from superset.automations.schemas import AutomationsTicketsResponseSchema
from superset.extensions import event_logger
from superset.utils import json
from superset.utils.core import send_email_smtp
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
            devin_response = self.devin_client.create_session(
                org_id=org_id,
                prompt=prompt,
            )

            session_id = devin_response.get("session_id", "")
            if not session_id:
                return self.response_500(
                    message="Devin API did not return a session_id"
                )

            # Step 2: Poll messages until Devin responds with bugs report
            logger.info("Polling Devin session %s for bugs report message", session_id)
            bugs_message = self.devin_client.poll_for_devin_message(
                org_id=org_id,
                session_id=session_id,
                poll_interval=config.DEVIN_POLL_INTERVAL,
                timeout=config.DEVIN_POLL_TIMEOUT,
            )

            # Step 3: Parse bugs JSON from the message
            bugs = self._parse_bugs_from_message(bugs_message)
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

    _TEMPLATES_DIR: str = os.path.join(os.path.dirname(__file__), "templates")

    @expose("/send_email", methods=("POST",))
    @event_logger.log_this
    @protect()
    @statsd_metrics
    @permission_name("send_email")
    def send_email(self) -> Response:
        """Send a bugs report email via the configured SMTP service.
        ---
        post:
          summary: Send a bugs report email
          description: >-
            Renders the bugs_report.html template with the provided bugs
            data and sends it to the recipient configured via
            AUTOMATIONS_EMAIL_RECIPIENT.
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  type: object
                  required:
                    - subject
                    - bugs
                    - session_id
                    - git_repo
                  properties:
                    subject:
                      type: string
                      description: Email subject line.
                    bugs:
                      type: array
                      description: List of bug objects from the Devin session.
                    session_id:
                      type: string
                      description: Devin session ID.
                    git_repo:
                      type: string
                      description: Target git repository.
          responses:
            200:
              description: Email sent successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      message:
                        type: string
            400:
              $ref: '#/components/responses/400'
            401:
              $ref: '#/components/responses/401'
            500:
              $ref: '#/components/responses/500'
        """
        config = AutomationsConfig()
        to = config.AUTOMATIONS_EMAIL_RECIPIENT
        if not to:
            return self.response_400(message="AUTOMATIONS_EMAIL_RECIPIENT is not configured")

        org_id = config.DEVIN_ORG_ID
        if not org_id:
            return self.response_400(message="DEVIN_ORG_ID is not configured")

        try:
            pr_metrics: PRMetrics = self.devin_client.get_pr_metrics(org_id=org_id)
            prs_closed_count = pr_metrics["prs_closed_count"]
            prs_created_count = pr_metrics["prs_created_count"]
            prs_merged_count = pr_metrics["prs_merged_count"]
            prs_opened_count = pr_metrics["prs_opened_count"]

            merge_rate = (prs_merged_count / prs_created_count) * 100
            close_rate = (prs_closed_count / prs_created_count) * 100

            env = Environment(
                loader=FileSystemLoader(os.path.join(self._TEMPLATES_DIR, "email")),
                autoescape=True,
            )
            template = env.get_template("bugs_report.html")
            html_content = template.render(
                merge_rate=merge_rate,
                close_rate=close_rate,
                open_prs=prs_opened_count,
                created_prs=prs_created_count,
            )
            send_email_smtp(
                to=to,
                subject="Devin Bug Swatting Report",
                html_content=html_content,
                config=current_app.config,
            )
            return self.response(200, message=f"Email sent to {to}")
        except Exception as ex:
            logger.exception("Failed to send email")
            return self.response_500(message=str(ex))

    _BUGS_REPORT_PREFIX: str = "Devin's Bugs Report: "

    def _parse_bugs_from_message(
        self,
        message_text: str,
    ) -> list[dict[str, Any]]:
        """Extract and parse the bugs JSON from a Devin session message.

        The message is expected to start with :pyattr:`_BUGS_REPORT_PREFIX`
        followed by a JSON array of bug objects.

        Args:
            message_text: The full text of the Devin message containing
                the bugs report.

        Returns:
            A list of bug dicts parsed from the message.

        Raises:
            ValueError: If the message does not contain the expected prefix
                or the JSON content is not a valid array.
        """
        if not message_text.startswith(self._BUGS_REPORT_PREFIX):
            raise ValueError(
                f"Message does not start with expected prefix: "
                f"{self._BUGS_REPORT_PREFIX!r}"
            )

        json_str = message_text[len(self._BUGS_REPORT_PREFIX) :]
        parsed = json.loads(json_str)
        if isinstance(parsed, list):
            return parsed
        logger.warning("Bugs report message content is not a JSON array")
        return []
