#!/bin/sh
# SUDO_ASKPASS helper for the Cisco AI PODs UI: answers sudo's password prompt from AIPOD_SUDO_PASSWORD, which the
# UI asks for when a job starts and keeps only in that job's environment (never saved to the vault or disk).
printf '%s\n' "${AIPOD_SUDO_PASSWORD:-}"
