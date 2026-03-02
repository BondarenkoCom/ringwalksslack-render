# Client Setup Guide

This guide explains how to configure the bot from scratch and where to get each token.

## 1. Files You Need

- Copy `.env.example` to `.env`
- Review `config.json`
- Start the app with:

```bash
python main.py serve
```

## 2. .env Values

Fill these values in `.env`:

```env
X_BEARER_TOKEN=
X_OAUTH2_CLIENT_ID=
X_OAUTH2_CLIENT_SECRET=
X_OAUTH2_REDIRECT_URI=
X_OAUTH2_SCOPES=tweet.read tweet.write users.read offline.access

SLACK_BOT_TOKEN=
SLACK_SIGNING_SECRET=
SLACK_CHANNEL_ID=
```

## 3. Slack Setup

### 3.1 Create the Slack App

1. Open the Slack app dashboard:
   https://api.slack.com/apps
2. Click `Create New App`
3. Choose `From scratch`
4. Pick your workspace

Official references:
- Slack app settings quickstart: https://docs.slack.dev/app-management/quickstart-app-settings
- Installing with OAuth: https://docs.slack.dev/authentication/installing-with-oauth

### 3.2 Add Bot Scopes

Open `OAuth & Permissions` and add these bot scopes:

- `chat:write`
- `commands`
- `channels:read`

Optional:

- `chat:write.public`

Use `chat:write.public` only if you want the bot to post in public channels without inviting it first.

If you change scopes later, reinstall the app to the workspace so the new token permissions take effect.

Reference:
- Scopes and OAuth install: https://docs.slack.dev/authentication/installing-with-oauth

### 3.3 Install the App

1. In `OAuth & Permissions`, click `Install to Workspace`
2. Approve the install
3. Copy `Bot User OAuth Token`

Put that value in:

```env
SLACK_BOT_TOKEN=xoxb-...
```

Use the `xoxb-...` bot token. Do not use `xapp-...` or temporary `xoxe...` tokens here.

Reference:
- Slack token types: https://docs.slack.dev/authentication/tokens/

### 3.4 Get the Signing Secret

1. Open `Basic Information`
2. Find `App Credentials`
3. Copy `Signing Secret`

Put it in:

```env
SLACK_SIGNING_SECRET=...
```

Use `Signing Secret`, not the old `Verification Token`.

Reference:
- Verifying requests from Slack: https://docs.slack.dev/authentication/verifying-requests-from-slack/

### 3.5 Add the Bot to the Channel

1. Open the target Slack channel
2. Invite the app:

```text
/invite @YourAppName
```

### 3.6 Get the Channel ID

Open the channel in Slack. The URL looks like:

```text
https://app.slack.com/client/T.../C...
```

Copy the `C...` value and put it in:

```env
SLACK_CHANNEL_ID=C...
```

Reference:
- Slack channel and conversation APIs: https://docs.slack.dev/reference/methods/conversations.list/

### 3.7 Configure Interactivity

Open `Interactivity & Shortcuts`:

- Turn `Interactivity` on
- Set `Request URL` to:

```text
https://your-public-url/slack/actions
```

Reference:
- Handling user interaction: https://docs.slack.dev/interactivity/handling-user-interaction/

### 3.8 Add the Slash Command

Open `Slash Commands`:

1. Create a command, for example:

```text
/fightbot
```

2. Set the request URL to:

```text
https://your-public-url/slack/command
```

3. Fill the required Slack fields like this:

```text
Short Description: Bot control commands
Usage Hint: help | health | usage | poll
```

4. Save

5. If Slack asks to reinstall the app to the workspace, do that so the command becomes available

Supported command text:

- `help`
- `health`
- `usage`
- `poll`

Examples:

```text
/fightbot help
/fightbot health
/fightbot usage
/fightbot poll
```

Reference:
- Slack slash commands: https://docs.slack.dev/interactivity/implementing-slash-commands/

## 4. X Setup

### 4.1 Open Your X App

Open your X developer app dashboard.

Official references:
- X developer apps fundamentals: https://docs.x.com/resources/fundamentals/developer-apps
- X OAuth 2 authorization code flow: https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code

### 4.2 Get the Bearer Token

In the app credentials / keys section, copy the app bearer token and put it in:

```env
X_BEARER_TOKEN=...
```

This token is used for search.

### 4.3 Get OAuth 2 Client Credentials

In the same X app, copy:

- `Client ID`
- `Client Secret`

Put them in:

```env
X_OAUTH2_CLIENT_ID=...
X_OAUTH2_CLIENT_SECRET=...
```

### 4.4 Set OAuth 2 Scopes

Make sure the app has these scopes:

- `tweet.read`
- `tweet.write`
- `users.read`
- `offline.access`

Put them in `.env` as:

```env
X_OAUTH2_SCOPES=tweet.read tweet.write users.read offline.access
```

Reference:
- X auth mapping for v2 endpoints: https://docs.x.com/fundamentals/authentication/guides/v2-authentication-mapping

### 4.5 Set the Redirect URI

Your redirect URI must match the public app URL:

```text
https://your-public-url/x/callback
```

Put it in:

```env
X_OAUTH2_REDIRECT_URI=https://your-public-url/x/callback
```

### 4.6 Complete the One-Time OAuth 2 Connection

After the server is running, open:

```text
https://your-public-url/x/connect
```

Approve the app in X.

Check status:

```bash
python main.py x-auth-status
```

Reference:
- Create Post / reply endpoint: https://docs.x.com/x-api/posts/create-post

## 5. Hosting Recommendation

Recommended option: Render Web Service.

Why:

- always-on process
- public HTTPS URL
- easy env var management
- simple health checks

Official references:
- Render pricing: https://render.com/pricing
- Render web services: https://render.com/docs/web-services
- Render health checks: https://render.com/docs/health-checks
- Render persistent disks: https://render.com/docs/disks
- Render default environment variables: https://render.com/docs/environment-variables
- Render free instance limitations: https://render.com/docs/free

Suggested Render settings:

- Runtime: Python
- App listens on `0.0.0.0:3000`
- Build command:

```bash
pip install -r requirements.txt
```

- Start command:

```bash
python main.py serve
```

### 5.1 Important Before You Deploy

Use a paid Render web service for this project.

Why:

- free web services can spin down on idle
- this bot needs to stay awake for polling and Slack callbacks
- SQLite state should be preserved across restarts and deploys
- Render persistent disks are available for paid services, not for free idle-preview style use

### 5.2 Put the Project in GitHub

The simplest Render flow is:

1. Create a GitHub repository
2. Upload this project folder
3. Push the code to GitHub

Then Render can deploy directly from that repository.

### 5.3 Create the Render Service

1. Sign in to Render
2. Click `New`
3. Choose `Web Service`
4. Choose `Build and deploy from a Git repository`
5. Connect your GitHub repo
6. Pick the repository that contains this project

### 5.4 Fill the Render Form

Use these values:

- `Runtime`: `Python 3`
- `Region`: choose the closest region to you
- `Branch`: your main branch
- `Root Directory`: leave blank if this project is at the repo root
- `Build Command`:

```bash
pip install -r requirements.txt
```

- `Start Command`:

```bash
python main.py serve
```

### 5.5 Set Environment Variables in Render

Open the service `Environment` section and add:

- `X_BEARER_TOKEN`
- `X_OAUTH2_CLIENT_ID`
- `X_OAUTH2_CLIENT_SECRET`
- `X_OAUTH2_REDIRECT_URI`
- `X_OAUTH2_SCOPES`
- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- `SLACK_CHANNEL_ID`

Also add:

```env
PORT=3000
```

Why:

- this app listens on port `3000`
- Render routes web traffic using the `PORT` environment variable

### 5.6 Add a Health Check

In the Render service settings, set:

```text
Health Check Path: /health
```

This lets Render monitor the bot and restart it if the web service stops responding.

### 5.7 Add a Persistent Disk

This project uses SQLite for dedupe, usage tracking, and stored OAuth data.

Without a persistent disk, Render uses an ephemeral filesystem, which means local files can be lost after a restart or redeploy.

Add a disk in the service `Advanced` or `Disks` section with:

- `Mount Path`:

```text
/opt/render/project/src/data
```

- `Size`: the smallest size that Render allows is enough for this project

Why this path:

- for Python services, Render stores source code under `/opt/render/project/src`
- this project stores runtime data in the local `data/` folder
- mounting the disk at `/opt/render/project/src/data` makes `data/state.db` persist

### 5.8 Create the Service

After the form and environment variables are set:

1. Click `Create Web Service`
2. Wait for the first deploy to finish
3. Open the service URL Render gives you

### 5.9 Connect Slack and X to the Render URL

Once the service is live, take the public Render URL and update:

- Slack interactivity URL:

```text
https://your-render-url/slack/actions
```

- Slack slash command URL:

```text
https://your-render-url/slack/command
```

- X OAuth2 redirect URI:

```text
https://your-render-url/x/callback
```

### 5.10 Complete the One-Time X OAuth2 Connection

Open:

```text
https://your-render-url/x/connect
```

Approve the app in X.

After that, the bot can use the stored OAuth2 user token.

### 5.11 Final Render Check

After deploy:

1. Take the public Render URL
2. Update Slack interactivity URL
3. Update Slack slash command URL
4. Update `X_OAUTH2_REDIRECT_URI`
5. Open `/x/connect` once

Then verify:

1. Open:

```text
https://your-render-url/health
```

2. Open:

```text
https://your-render-url/x/status
```

3. In Slack run:

```text
/fightbot health
/fightbot usage
/fightbot poll
```

4. Confirm that new alerts appear in the Slack channel

## 6. Quick Verification Checklist

After setup, verify these:

1. Health endpoint:

```text
https://your-public-url/health
```

2. X status endpoint:

```text
https://your-public-url/x/status
```

3. Slack commands:

```text
/fightbot health
/fightbot usage
/fightbot poll
```

4. New Slack alerts show:

- `Open X`
- `Reply A`
- `Reply B`
- `Ignore`

## 7. Important X Limitation

As of February 23, 2026, X announced that programmatic replies via `POST /2/tweets` are restricted for self-serve API tiers unless the original author mentions the account or quotes its post.

For this bot, that means:

- detection flow works
- Slack alerts work
- `Open X` works
- some API replies to arbitrary public search matches may still be rejected by X

Official references:

- X Developers announcement: https://x.com/XDevelopers/status/2026084506822730185
- X automation rules: https://help.x.com/en/rules-and-policies/x-automation
- X Create Post docs: https://docs.x.com/x-api/posts/create-post
