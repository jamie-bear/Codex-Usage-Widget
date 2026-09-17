# Local Codex Usage Widget

A small localhost-only page showing the remaining Codex usage attached to your ChatGPT plan, including reset times.

It uses the Codex CLI's local App Server method `account/rateLimits/read`. It does not read `~/.codex/auth.json`, browser cookies, OAuth tokens, or call the private ChatGPT usage endpoint itself.

## Requirements

1. Codex CLI installed and signed in with the same ChatGPT account you use in Codex Desktop.
   - Check with: `codex --version`
   - If needed, run `codex` and complete ChatGPT sign-in.
2. Python 3.10+.

## macOS 26

Double-click `start-macos.command`.

If macOS blocks the downloaded script, open Terminal in this folder and run:

```zsh
chmod +x start-macos.command
./start-macos.command
```

If `python3` is missing and you use Homebrew:

```zsh
brew install python
```

## Windows 11

Double-click `start-windows.cmd`.

If Python is missing, one option is:

```powershell
winget install Python.Python.3.13
```

Close/reopen your terminal after installation, then run `start-windows.cmd` again.

## Direct use

```text
python codex_usage_widget.py
python codex_usage_widget.py --port 9876
python codex_usage_widget.py --no-browser
```

The page binds only to `127.0.0.1`, so it is not exposed to other machines on your LAN. By default it opens at:

```text
http://127.0.0.1:8765/
```

The browser refreshes once per minute. The Python server caches readings briefly so repeated page loads do not hammer the App Server.

Click **Refresh** to bypass the cache and request a new reading. **Kill process** stops the widget server and its own Codex helper on macOS and Windows; other Codex tasks stay running. Start the launcher again to reopen the widget.

The tab title updates with each reading, for example `Codex Usage | 89% w` or `Codex Usage | 75% 5h`. When both windows are available, it shows the one with the least remaining usage. If an update fails, the title shows `Codex Usage | Update failed` until the next successful refresh.

## Troubleshooting

### `Could not find the codex CLI in PATH`

Open a new Terminal/PowerShell window and run:

```text
codex --version
```

If that command does not work, install/reinstall Codex CLI first.

### Authentication / rate-limit error

Run `codex login status` in Terminal/PowerShell. If it reports `Not logged in`, run `codex login`, complete the browser sign-in with the account you use in Desktop, then click **Refresh**. The CLI helper needs its own sign-in; an active Codex Desktop session alone is not sufficient. Use ChatGPT authentication rather than only an API key.

### `error sending request for url (https://chatgpt.com/backend-api/wham/usage)`

The Codex CLI could not connect to ChatGPT. The widget reconnects and retries once after a short delay. Check your internet connection, VPN, proxy, or firewall, then click **Refresh**. A failed update keeps the last successful reading and its timestamp visible.

On macOS, the widget passes system HTTP/HTTPS proxy settings to the CLI when equivalent environment variables are not already set. Explicit `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` settings take precedence. Automatic proxy configuration (PAC) scripts are not evaluated; those networks may need explicit proxy variables.

Launch the widget from Finder or Explorer. A process launched inside a Codex terminal with networking disabled inherits that restriction and cannot fetch usage; the widget now detects that environment at startup. For sign-in errors, run `codex login` and refresh again.

After updating these files, stop the old widget with Ctrl+C in its terminal and run the launcher again to load the changes.

### Port already in use

Choose another port:

```text
python codex_usage_widget.py --port 9876
```

## Scope

This reports the Codex rate-limit windows that are charged against your ChatGPT plan. It is not a universal meter for every ChatGPT product/message limit.
