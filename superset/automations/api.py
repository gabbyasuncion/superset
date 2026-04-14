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

from flask import current_app, Response
from flask_appbuilder import expose
from flask_appbuilder.security.decorators import permission_name, protect
from jinja2 import Environment, FileSystemLoader

from superset.automations.config import AutomationsConfig
from superset.automations.devin_client import DevinClient, PRMetrics
from superset.automations.schemas import AutomationsTicketsResponseSchema
from superset.extensions import event_logger
from superset.utils import json
from superset.utils.core import send_email_smtp
from superset.views.base_api import BaseSupersetApi, statsd_metrics

logger = logging.getLogger(__name__)


class AutomationsRestApi(BaseSupersetApi):
    """Automations Admin API.

    Provides endpoints for automated workflows such as identifying bugs
    via the Devin API and prompting Devin to open PRs for each bug.
    Access is restricted to authorized internal users via JWT tokens
    minted by the ``/api/v1/security/login`` endpoint.

    The Devin HTTP client is initialized once and reused across requests
    and endpoints via :pymeth:`_get_devin_client`.
    """

    resource_name = "automations"
    allow_browser_login = False
    openapi_spec_tag = "Automations"
    openapi_spec_component_schemas = (AutomationsTicketsResponseSchema,)

    _devin_client: DevinClient | None = None

    def _get_devin_client(self) -> DevinClient:
        """Return a reusable Devin API client, creating one if needed.

        This is intentionally a regular method rather than a ``@property``
        so that Flask-AppBuilder's ``__init__`` attribute introspection
        (which calls ``getattr(self, attr)`` on every name in ``dir()``)
        does not trigger eager ``DevinClient`` construction — which would
        raise ``ValueError`` when ``DEVIN_API_KEY`` is absent.
        """
        if self._devin_client is None:
            self.__class__._devin_client = DevinClient()
        return self._devin_client  # type: ignore[return-value]

    @expose("/bug_swatter", methods=("POST",))
    @event_logger.log_this
    @protect()
    @statsd_metrics
    @permission_name("bug_swatter")
    def bug_swatter(self) -> Response:
        """Identify bugs via Devin and prompt PRs for each.
        ---
        post:
          summary: Identify bugs and prompt Devin to open PRs
          description: >-
            Uses the Devin API to identify bugs in the superset
            repository and sends a message back to the session
            prompting Devin to open a PR for each bug found.
          responses:
            200:
              description: PR prompts sent successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      session_id:
                        type: string
                      pr_prompts_sent:
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
            prompt = self._get_devin_client().build_bug_identification_prompt(
                num_bugs=num_bugs,
                git_repo=git_repo,
            )
            devin_response = self._get_devin_client().create_session(
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
            bugs_message = self._get_devin_client().poll_for_devin_message(
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

            return self.response(
                200,
                session_id=session_id,
                bugs_found=bugs,
                bugs_requested=num_bugs,
            )

        except TimeoutError as ex:
            logger.error("Devin session polling timed out: %s", ex)
            return self.response_500(message=str(ex))
        except ValueError as ex:
            logger.error("Configuration error: %s", ex)
            return self.response_400(message=str(ex))
        except Exception as ex:
            logger.exception("Failed to run bug swatter automation")
            return self.response_500(message=str(ex))

    _TEMPLATES_DIR: str = os.path.join(os.path.dirname(__file__), "templates")

    @expose("/report", methods=("POST",))
    @event_logger.log_this
    @protect()
    @statsd_metrics
    @permission_name("report")
    def report(self) -> Response:
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
            return self.response_400(
                message="AUTOMATIONS_EMAIL_RECIPIENT is not configured"
            )

        org_id = config.DEVIN_ORG_ID
        if not org_id:
            return self.response_400(message="DEVIN_ORG_ID is not configured")

        try:
            pr_metrics: PRMetrics = self._get_devin_client().get_pr_metrics(
                org_id=org_id
            )
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
