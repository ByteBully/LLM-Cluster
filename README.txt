LLMCluster is a Windows 11 desktop application for running large language models across multiple NVIDIA GPUs on different computers using Tailscale, WSL2, and llama.cpp RPC.

Features

Modern English interface built with PySide6 and QML.

One-click HOST and WORKER setup.

Automatic WSL2, Ubuntu, CUDA, and llama.cpp configuration.

Tailscale peer discovery and remote GPU connectivity.

Local GGUF model detection.

Diagnostics, logs, and advanced configuration.

Requirements

Windows 11

Python 3.11+

NVIDIA GPU with compatible drivers

Internet connection

Administrator privileges

Installation

pip install -r requirements.txt
python app.py

Quick Start

Launch GPUCluster as administrator.

Select WORKER on the remote computer and complete setup.

Select HOST on the main computer.

Connect both devices to the same Tailscale network.

Discover the WORKER and select a local GGUF model.

Launch the LLM server.

Notes

The HOST runs the model API, while the WORKER provides additional GPU resources through RPC.

Initial setup may require a Windows restart and Tailscale authentication.

Status: Experimental software. Windows, WSL2, CUDA, and network configurations may require troubleshooting.