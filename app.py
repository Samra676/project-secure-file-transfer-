# app.py
import os
import secrets
import shutil
import subprocess
import time
import json
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify

import yaml

BASE_DIR = Path(__file__).resolve().parent
SESSIONS_DIR = BASE_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_urlsafe(16)

# Utility: create ephemeral ed25519 keypair
def generate_ephemeral_keypair(session_path: Path):
    key_path = session_path / "id_ed25519"
    pub_path = session_path / "id_ed25519.pub"
    # remove existing if any
    if key_path.exists():
        key_path.unlink()
    if pub_path.exists():
        pub_path.unlink()
    cmd = ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", ""]
    subprocess.run(cmd, check=True)
    pubkey = pub_path.read_text().strip()
    return str(key_path), pubkey

def write_inventory(session_path: Path, host, user, private_key_path):
    inv = session_path / "inventory.ini"
    content = f"""[target]
client ansible_host={host} ansible_user={user} ansible_ssh_private_key_file={private_key_path}
"""
    inv.write_text(content)
    return str(inv)

def write_vars_file(session_path: Path, src_paths, dest_path, client_user, public_key):
    varsf = session_path / "vars.yml"
    data = {
        "src_paths": src_paths,
        "dest_path": dest_path,
        "client_user": client_user,
        "public_key": public_key
    }
    varsf.write_text(yaml.safe_dump(data))
    return str(varsf)

def compute_total_size(paths):
    total = 0
    for p in paths:
        if os.path.isfile(p):
            total += os.path.getsize(p)
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        pass
    return total

def run_ansible_playbook(inv_path, playbook_path, extra_vars_file, logfile_path):
    # call ansible-playbook, capture stdout/stderr to logfile
    cmd = [
        "ansible-playbook",
        "-i", inv_path,
        str(playbook_path),
        "--extra-vars", f"@{extra_vars_file}"
    ]
    with open(logfile_path, "wb") as logf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in proc.stdout:
            logf.write(line)
            logf.flush()
        proc.wait()
    return proc.returncode

@app.route("/")
def index():
    # simple UI: enter comma-separated src paths and dest path
    return render_template("index.html")

@app.route("/create_session", methods=["POST"])
def create_session():
    # src_paths text, dest_path, optional note
    src_text = request.form.get("src_paths", "").strip()
    dest_path = request.form.get("dest_path", "/home/ubuntu/received_files").strip()
    if not src_text:
        return "Please provide source paths (comma-separated)", 400
    src_paths = [s.strip() for s in src_text.split(",") if s.strip()]
    token = secrets.token_urlsafe(12)
    session_path = SESSIONS_DIR / token
    session_path.mkdir(parents=True, exist_ok=False)
    # store meta
    meta = {
        "token": token,
        "created_at": time.time(),
        "src_paths": src_paths,
        "dest_path": dest_path,
        "status": "waiting_for_client"
    }
    (session_path / "meta.json").write_text(json.dumps(meta, indent=2))
    # generate ephemeral keypair
    priv_key_path, pubkey = generate_ephemeral_keypair(session_path)
    # save public key in meta
    meta['public_key'] = pubkey
    (session_path / "meta.json").write_text(json.dumps(meta, indent=2))
    share_link = request.host_url.rstrip("/") + url_for("accept", token=token)
    return redirect(url_for("share", token=token))

@app.route("/share/<token>")
def share(token):
    session_path = SESSIONS_DIR / token
    if not session_path.exists():
        return "Invalid token", 404
    meta = json.loads((session_path / "meta.json").read_text())
    public_key = meta.get("public_key", "")
    # show link + public key to paste on client's machine
    accept_url = request.host_url.rstrip("/") + url_for("accept", token=token)
    return render_template("share.html", token=token, accept_url=accept_url, public_key=public_key)

@app.route("/accept/<token>", methods=["GET","POST"])
def accept(token):
    session_path = SESSIONS_DIR / token
    if not session_path.exists():
        return "Invalid or expired token", 404
    meta = json.loads((session_path / "meta.json").read_text())
    if request.method == "GET":
        # show public key + instructions for client to add public key to their ~/.ssh/authorized_keys
        return render_template("accept.html", token=token, public_key=meta.get("public_key",""), dest_path=meta.get("dest_path","/home/ubuntu/received_files"))
    # POST: client submitted host and user -> trigger ansible
    client_host = request.form.get("client_host").strip()
    client_user = request.form.get("client_user").strip()
    dest_path = request.form.get("dest_path").strip() or meta.get("dest_path")
    if not client_host or not client_user:
        return "Provide client_host and client_user", 400
    # update meta
    meta['client_host'] = client_host
    meta['client_user'] = client_user
    meta['dest_path'] = dest_path
    meta['status'] = 'starting_transfer'
    (session_path / "meta.json").write_text(json.dumps(meta, indent=2))

    priv_key = str(session_path / "id_ed25519")
    inv_path = write_inventory(session_path, client_host, client_user, priv_key)
    vars_path = write_vars_file(session_path, meta['src_paths'], dest_path, client_user, meta['public_key'])
    # compute expected size
    total_bytes = compute_total_size(meta['src_paths'])
    meta['expected_size_bytes'] = total_bytes
    meta['started_at'] = time.time()
    (session_path / "meta.json").write_text(json.dumps(meta, indent=2))

    # run ansible transfer playbook
    playbook_transfer = BASE_DIR / "playbooks" / "transfer.yml"
    logfile = session_path / "ansible_transfer.log"
    rc = run_ansible_playbook(inv_path, playbook_transfer, vars_path, logfile)
    meta['transfer_rc'] = rc
    meta['transfer_logfile'] = str(logfile)
    meta['finished_at'] = time.time()
    if rc == 0:
        meta['status'] = 'transfer_success'
    else:
        meta['status'] = 'transfer_failed'
    (session_path / "meta.json").write_text(json.dumps(meta, indent=2))

    # run cleanup to remove ephemeral public key from remote authorized_keys
    playbook_cleanup = BASE_DIR / "playbooks" / "cleanup.yml"
    logfile2 = session_path / "ansible_cleanup.log"
    rc2 = run_ansible_playbook(inv_path, playbook_cleanup, vars_path, logfile2)
    meta['cleanup_rc'] = rc2
    meta['cleanup_logfile'] = str(logfile2)
    (session_path / "meta.json").write_text(json.dumps(meta, indent=2))

    # write a simple report
    report = {
        "token": token,
        "status": meta['status'],
        "src_paths": meta['src_paths'],
        "dest_path": dest_path,
        "client_host": client_host,
        "client_user": client_user,
        "expected_size_bytes": total_bytes,
        "started_at": meta['started_at'],
        "finished_at": meta['finished_at'],
        "transfer_rc": meta.get('transfer_rc'),
        "cleanup_rc": meta.get('cleanup_rc')
    }
    (session_path / "report.json").write_text(json.dumps(report, indent=2))

    return redirect(url_for("status", token=token))

@app.route("/status/<token>")
def status(token):
    session_path = SESSIONS_DIR / token
    if not session_path.exists():
        return "Invalid token", 404
    meta = json.loads((session_path / "meta.json").read_text())
    # show meta + tail of ansible log
    def tail(filename, n=200):
        p = session_path / filename
        if not p.exists():
            return ""
        data = p.read_text(errors='ignore').splitlines()
        return "\n".join(data[-n:])
    transfer_log = tail("ansible_transfer.log")
    cleanup_log = tail("ansible_cleanup.log")
    report = session_path.joinpath("report.json").read_text() if (session_path / "report.json").exists() else "{}"
    return render_template("status.html", meta=meta, transfer_log=transfer_log, cleanup_log=cleanup_log, report=report)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
