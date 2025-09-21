# project-secure-file-transfer-
# Secure Automated File Transfer System

This project securely transfers large media files (images/videos) between distant systems using **Python + Flask + Ansible + SSH** without relying on third-party services.

---

## Features
- On-demand file transfer via web interface.
- Secure SSH connection between sender and receiver.
- Automated transfer using Ansible playbooks.
- Real-time progress display.
- Logging and reports after completion.
- No database — lightweight and session-based.

---

## Project Structure

secure_file_transfer/
│
├── app.py # Flask backend
├── requirements.txt # Python dependencies
├── templates/ # HTML templates
│ ├── index.html
│ ├── share.html
│ ├── accept.html
│ └── status.html
└── playbooks/ # Ansible playbooks
├── transfer.yml
└── cleanup.yml


---

## Prerequisites

### On the Sender Machine (your machine)
- Python 3.8+ installed.
- Ansible, SSH, and Rsync installed:
  ```bash
  sudo apt update
  sudo apt install -y ansible rsync openssh-client openssh-server
  sudo systemctl enable --now ssh

    Virtual environment enabled.

On the Receiver Machine (client)

    SSH server enabled.

    Will add a temporary public key to ~/.ssh/authorized_keys (the app shows the key).

Installation & Setup

    Clone / Unzip the Project:

unzip secure_file_transfer_fixed.zip -d secure_file_transfer
cd secure_file_transfer

Create Virtual Environment:

python3 -m venv venv
source venv/bin/activate

Install Dependencies:

    pip install -r requirements.txt

Running the Application

    Start Flask Server:

python3 app.py

The app runs at http://127.0.0.1:5000

    .

    Open Browser:

        Go to http://127.0.0.1:5000

        Select source paths and destination path.

        Generate and share the link with the client.

    Client Accepts Transfer:

        Adds the public key to their ~/.ssh/authorized_keys.

        Opens the provided link and clicks “Accept”.

    Transfer Progress & Logs:

        The status page displays transfer logs and cleanup logs.

        After transfer completion, the app cleans up the temporary keys.

Playbooks

    transfer.yml — Handles the file transfer.

    cleanup.yml — Removes the temporary public key from the client after the transfer.

Notes

    Always use absolute paths for source and destination.

    Ensure SSH connectivity between sender and client before running the app.

    This system is designed to run on-demand (no persistent DB).

