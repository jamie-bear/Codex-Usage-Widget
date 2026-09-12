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

The tab title updates with each reading, for example `Codex Usage | 89% w` or `Codex Usage | 75% 5h`. When both windows are available, it shows the one with the least remaining usage. If an update fails, the title shows `Codex Usage | Update failed` until the next successful refresh.

## Troubleshooting

### `Could not find the codex CLI in PATH`

Open a new Terminal/PowerShell window and run:

```text
codex --version
```

If that command does not work, install/reinstall Codex CLI first.

### Authentication / rate-limit error

Run `codex`, confirm you are signed in with ChatGPT rather than only using an API key, and then restart the widget.

### Port already in use

Choose another port:

```text
python codex_usage_widget.py --port 9876
```

## Scope

This reports the Codex rate-limit windows that are charged against your ChatGPT plan. It is not a universal meter for every ChatGPT product/message limit.
