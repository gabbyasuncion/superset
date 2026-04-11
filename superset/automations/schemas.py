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

from marshmallow import fields, Schema


class AutomationsTicketsResponseSchema(Schema):
    """Schema for the POST /api/v1/automations/tickets response."""

    session_id = fields.String(
        metadata={"description": "The Devin session ID used to identify bugs"}
    )
    tickets_created = fields.List(
        fields.Dict(),
        metadata={"description": "List of Jira tickets created"},
    )
    bugs_requested = fields.Integer(
        metadata={"description": "Number of bugs requested"}
    )
