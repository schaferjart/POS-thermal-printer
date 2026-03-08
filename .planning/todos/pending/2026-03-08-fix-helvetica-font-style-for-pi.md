---
created: 2026-03-08T13:27:17.772Z
title: Fix helvetica font style for Pi
area: general
files:
  - config.yaml
  - md_renderer.py
---

## Problem

The `helvetica` font style in config.yaml references macOS-only font paths (`/System/Library/Fonts/HelveticaNeue.ttc`) which don't exist on the Raspberry Pi (Debian Trixie). This means the helvetica style is unusable on the Pi deployment.

## Solution

Add fallback font paths that exist on Linux/Debian (e.g. `/usr/share/fonts/truetype/dejavu/` or similar). Could use a list of paths per font entry and pick the first that exists, or add Linux-specific paths alongside macOS ones in config.yaml.
