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

import os


class AutomationsConfig:
    """Configuration for the Automations Admin API.

    Environment variables are read at instantiation time so that
    values are always up-to-date per request.
    """

    # Static defaults
    DEVIN_API_BASE_URL: str = "https://api.devin.ai"
    JIRA_BASE_URL: str = "https://gabrielaasuncion.atlassian.net"
    JIRA_ASSIGNEE_NAME: str = "Devin Bug Hunter"
    JIRA_BUG_LABEL: str = "!bug_fix_pr"
    TARGET_GIT_REPO: str = "gabbyasuncion/superset"

    def __init__(self) -> None:
        self.NUM_BUGS: int = int(os.environ.get("AUTOMATIONS_NUM_BUGS", "5"))
        self.DEVIN_ORG_ID: str = os.environ.get("DEVIN_ORG_ID", "")
        self.JIRA_PROJECT_KEY: str = os.environ.get("JIRA_PROJECT_KEY", "SUP")
        self.JIRA_ASSIGNEE_ACCOUNT_ID: str = os.environ.get(
            "JIRA_ASSIGNEE_ACCOUNT_ID", ""
        )
