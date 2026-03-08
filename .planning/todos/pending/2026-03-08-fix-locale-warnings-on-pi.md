---
created: 2026-03-08T13:27:17.772Z
title: Fix locale warnings on Pi
area: tooling
files:
  - setup.sh
---

## Problem

The Raspberry Pi (Debian Trixie) shows locale warnings during operation, likely because the required locale (e.g. `en_US.UTF-8`) isn't generated. This produces noisy stderr output.

## Solution

Add `sudo dpkg-reconfigure locales` (or `sudo locale-gen en_US.UTF-8`) to `setup.sh` so locales are configured automatically during initial deployment.
