#!/bin/sh
# GIT_ASKPASS helper for the Cisco AI PODs UI: answers the username prompt from AIPOD_GIT_USERNAME
# and the password prompt from GIT_TOKEN (loaded from the local git vault, never written to disk).
case "$1" in
    Username*) printf '%s\n' "${AIPOD_GIT_USERNAME:-x-access-token}" ;;
    *) printf '%s\n' "${GIT_TOKEN:-}" ;;
esac
