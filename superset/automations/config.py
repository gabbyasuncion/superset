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
    """Configuration for the Automations Admin API."""

    # Number of bugs to identify in the superset repo
    NUM_BUGS: int = int(os.environ.get("AUTOMATIONS_NUM_BUGS", "5"))

    # Devin API organization ID
    DEVIN_ORG_ID: str = os.environ.get("DEVIN_ORG_ID", "")

    # Devin API base URL
    DEVIN_API_BASE_URL: str = "https://api.devin.ai"

    # Jira instance base URL
    JIRA_BASE_URL: str = "https://gabrielaasuncion.atlassian.net"

    # Jira project key for bug tickets
    JIRA_PROJECT_KEY: str = os.environ.get("JIRA_PROJECT_KEY", "SUP")

    # Jira assignee display name
    JIRA_ASSIGNEE_NAME: str = "Devin Bug Hunter"

    # Jira bug label
    JIRA_BUG_LABEL: str = "!bug_fix_pr"

    # Git repo for bug identification
    TARGET_GIT_REPO: str = "gabbyasuncion/superset"
