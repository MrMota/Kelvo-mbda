KELVO FOR WINDOWS (no Docker)
=============================

Kelvo runs on this PC with Python. Ollama runs the models on your NVIDIA GPU.
You use Kelvo in Edge or Chrome, installed as an app - on this PC and on your phone.

WHAT'S IN THIS FOLDER
  install.cmd        install or update Kelvo (double-click)
  enable-phone.cmd   set up phone access with Tailscale, shows your server address
  start-kelvo.cmd    start Kelvo (if stopped) and open it
  stop-kelvo.cmd     stop Kelvo (it starts again at your next sign-in)
  uninstall.cmd      remove Kelvo (asks before deleting your data)
  kelvo-*.whl        Kelvo itself - keep it next to install.cmd

1. INSTALL
  - Double-click install.cmd.
    It checks for Python 3.10+ and Ollama (and offers to install them with winget),
    installs Kelvo into %LOCALAPPDATA%\Kelvo, asks for the username and password
    you will sign in with, starts Kelvo, and opens http://127.0.0.1:7860
  - Kelvo then starts by itself in the background each time you sign in to Windows.
  - First time only: Windows may warn about running a downloaded file. Choose
    "More info" > "Run anyway" (or right-click the .zip > Properties > Unblock before unzipping).

2. PICK A MODEL
  - In a terminal:  ollama pull qwen3:30b   (about 19 GB; fits fully in a 32 GB GPU)
                    ollama pull nomic-embed-text
  - In Kelvo: Settings > Models > Default model = qwen3:30b.
    Agents need a model tagged "tools".
  - Check it runs on the GPU: send a message, then run  ollama ps  -> "100% GPU".

3. INSTALL IT AS AN APP ON THIS PC
  - Edge:   ... menu > Apps > Install Kelvo
  - Chrome: the install icon at the right end of the address bar
  It gets its own window, Start-menu entry and taskbar icon.

4. USE KELVO ON YOUR PHONE
  - Install Tailscale on this PC (https://tailscale.com/download/windows) and sign in.
  - In the Tailscale admin console (login.tailscale.com) > DNS:
    turn on MagicDNS and HTTPS Certificates.
  - Double-click enable-phone.cmd. It prints YOUR SERVER ADDRESS, like
        https://desktop-abc123.tail1a2b3c.ts.net
  - On the phone: install Tailscale, sign in with the same account, open that address.
    Android Chrome: menu > Install app.   iPhone Safari: Share > Add to Home Screen.
    (Or type the address into the Kelvo Android app.)
  - Never run "tailscale funnel": that would put Kelvo on the public internet.

UPDATING
  Put the new kelvo-*.whl next to install.cmd and double-click install.cmd again.
  Your flows, skills, chats and account are kept.

WHERE THINGS ARE
  Program:  %LOCALAPPDATA%\Kelvo\venv
  Log:      %LOCALAPPDATA%\Kelvo\kelvo.log
  Data:     %USERPROFILE%\.kelvo\kelvo.db   (back it up: copy this file while Kelvo is stopped,
            or run  %LOCALAPPDATA%\Kelvo\venv\Scripts\kelvo.exe backup )
  Forgot your password:  %LOCALAPPDATA%\Kelvo\venv\Scripts\kelvo.exe set-password
