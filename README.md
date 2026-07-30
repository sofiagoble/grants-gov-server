# grants-gov MCP server

Hosted counterpart to the `hispanic-latam-grants` Cowork plugin's `find-grants` skill. Wraps the real [Simpler Grants API](https://api.simpler.grants.gov) (the modernized replacement for legacy grants.gov search) behind an MCP tool interface, so the skill gets structured, authenticated search instead of scraping public pages.

This is kept **separate from the plugin's installable `.plugin` file** — installers only need `.mcp.json` pointing at wherever you deploy this, not the server source itself.

## 1. Get a free Simpler Grants API key

1. Go to [simpler.grants.gov](https://simpler.grants.gov) and sign in with **Login.gov** (free — email + password, no cost).
2. Go to the developer/API section ("Manage API Keys") and click **Create API Key**. It's issued instantly.

Keep this key secret — it goes on the server you deploy below, never into the plugin itself or anywhere installers can see it.

## 2. Deploy the server

This is a standard Docker container (`Dockerfile` included) exposing one HTTP port — it works on any platform that runs a container from a `Dockerfile` and lets you set environment variables. A few reasonable options, roughly ordered by how little setup they need:

- **[Render](https://render.com)** — has a genuinely free tier for a single web service. The tradeoff: a free-tier service spins down after inactivity, so the first request after idle time takes a few extra seconds (a "cold start"). Fine for low-traffic use; upgrade to a paid instance later if that delay becomes annoying.
- **[Railway](https://railway.app)** — similarly simple, small usage-based cost after a trial credit runs out.
- **[Fly.io](https://fly.io)** — free allowance for small apps, a bit more CLI-driven to set up.
- **DigitalOcean App Platform** — what the original `grant-finder` plugin this was inspired by uses; more manual setup than the above, no meaningfully free tier.

Whichever you pick, the steps are the same shape:

1. Connect/point the platform at this folder (or push it to a small git repo first — most platforms deploy from a repo).
2. Set the environment variable `SIMPLER_GRANTS_API_KEY` to the key from step 1 (as a "secret," not a plain env var, if the platform distinguishes between them).
3. Deploy. The platform will build the `Dockerfile` and give you a public HTTPS URL.

## 3. Point the plugin at your deployed server

Once deployed, you'll have a URL like `https://your-service-name.onrender.com`. The MCP endpoint path depends on how the platform routes to the container's port 8000 — try `https://your-service-name.onrender.com/mcp` first (this is the FastMCP SDK's default streamable-HTTP mount path). If a test request to that URL doesn't get a response, check your platform's logs for the actual path FastMCP registered, and adjust.

Update `.mcp.json` in the plugin folder (`hispanic-latam-grants/.mcp.json`) with that URL, replacing the placeholder:

```json
{
  "mcpServers": {
    "grants-gov": {
      "type": "http",
      "url": "https://your-service-name.onrender.com/mcp"
    }
  }
}
```

Then re-zip and re-upload the plugin. `mcp.config.dev.json` (pointing at `localhost:8000`) is there if you want to run the server locally first with `python3 server.py` (after `pip install -r requirements.txt` and exporting `SIMPLER_GRANTS_API_KEY`) to confirm it works before deploying anywhere.

## 4. What happens if this server goes down

The skill is written to fall back to its own WebSearch/WebFetch method automatically if this server is unreachable, and to say so explicitly in its output (something like "the live federal-grants connector was unreachable, results used the backup method") — so a plugin user sees a visible note rather than a silent failure, and results degrade rather than break outright. You'll only find out this happened if someone tells you, or if you set up separate uptime monitoring (e.g. a free [UptimeRobot](https://uptimerobot.com) check against your deployed URL) — this server has no built-in alerting of its own.

## Local development

```bash
pip install -r requirements.txt
export SIMPLER_GRANTS_API_KEY=your-key-here
python3 server.py
```

Serves on `http://localhost:8000/mcp` by default (override with the `PORT` env var).
