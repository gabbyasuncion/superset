<!--
Licensed to the Apache Software Foundation (ASF) under one
or more contributor license agreements.  See the NOTICE file
distributed with this work for additional information
regarding copyright ownership.  The ASF licenses this file
to you under the Apache License, Version 2.0 (the
"License"); you may not use this file except in compliance
with the License.  You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
-->

# Running My Automation System

## Installation

1. **Fork and clone the Superset repo**
   Fork [gabbyasuncion/superset](https://github.com/gabbyasuncion/superset) and clone it locally.

2. **Install Act** — enables you to run GitHub Actions locally.
   Recommended: install GitHub CLI and add the `act` extension:
```bash
   gh extension install https://github.com/nektos/gh-act
```

3. **Install Docker** — easy way to start up the server, DBs, Redis, etc.

---

## Setup

### 1. Create a local environment file
```bash
cp docker/.env-local.example docker/.env-local
```

### 2. Configure the Devin API client

1. Configure your fork of the Superset repo in an existing (or new) Devin org.
2. Go to **Settings → Membership → Service users**.
3. Click **"Provision service user"**.
4. Grant **"Member"** organization role with a **7-day expiration**.
5. In `~/superset/docker/.env-local`, set:
   - `DEVIN_API_KEY` — the generated token
   - `DEVIN_ORG_ID` — the organization ID (found on the Service Users page)

### 3. Configure Gmail as your email host
> Free for up to 500 emails/day!

1. Go to your **Google Account → Security**.
2. Enable **2-Step Verification** (required).
3. Go to **Security → 2-Step Verification → App passwords**.
4. Create a new app password and copy the 16-character code.
5. In `docker/.env-local`, set:
   - `SMTP_PASSWORD` — the app password from the previous step
   - `AUTOMATIONS_EMAIL_RECIPIENT`, `SMTP_USER`, and `SMTP_MAIL_FROM` — your Gmail address

### 4. Start Superset locally
```bash
docker compose up
```

---

## Running the GitHub Actions

### Bug Swatter (Bi-Weekly)
Scans the codebase to identify bugs and opens PRs to fix them.

```bash
gh act schedule -W .github/workflows/bug_swatter.yml \
  --secret ADMIN_API_USERNAME=admin \
  --secret ADMIN_API_PASSWORD=admin
```

> **M1 Mac?** Add these recommended flags:
> ```bash
> --container-architecture linux/amd64
> -P ubuntu-latest=catthehacker/ubuntu:act-22.04
> ```

Once running, use the output session ID to open the session in the Devin UI, or navigate to GitHub to see Devin's PRs.

---

### Bug Swatter Report (Monthly)
Reports on Devin's bug-fixing activity over the past month.

```bash
gh act schedule -W .github/workflows/bug_swatter_report.yml \
  --secret ADMIN_API_USERNAME=admin \
  --secret ADMIN_API_PASSWORD=admin
```

> **M1 Mac?** Add these recommended flags:
> ```bash
> --container-architecture linux/amd64
> -P ubuntu-latest=catthehacker/ubuntu:act-22.04
> ```

Once complete, you'll receive an email at `AUTOMATIONS_EMAIL_RECIPIENT` with Devin API PR metrics for the last month.
