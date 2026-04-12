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
    TARGET_GIT_REPO: str = "gabbyasuncion/superset"
    # Terminal statuses indicating the Devin session has finished
    DEVIN_TERMINAL_STATUSES: tuple[str, ...] = ("exit", "error", "suspended")

    def __init__(self) -> None:
        # Number of bugs to identify in the superset repo
        self.NUM_BUGS: int = int(os.environ.get("AUTOMATIONS_NUM_BUGS", "5"))

        # Devin API organization ID
        self.DEVIN_ORG_ID: str = os.environ.get("DEVIN_ORG_ID", "")

        # Devin session polling configuration
        self.DEVIN_POLL_INTERVAL: int = int(os.environ.get("DEVIN_POLL_INTERVAL", "30"))
        self.DEVIN_POLL_TIMEOUT: int = int(os.environ.get("DEVIN_POLL_TIMEOUT", "1800"))

        # Email recipient for bug report notifications
        self.AUTOMATIONS_EMAIL_RECIPIENT: str = os.environ.get(
            "AUTOMATIONS_EMAIL_RECIPIENT", ""
        )
