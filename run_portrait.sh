#!/bin/bash
export OPENROUTER_API_KEY="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"
python3 print_cli.py --dummy portrait "$@" --skip-selection
