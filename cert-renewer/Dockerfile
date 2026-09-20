FROM smallstep/step-cli:0.30.2

# The base image's default user (`step`, uid 1000) can't install packages, and at runtime
# needs root-equivalent access to the mounted Docker socket anyway (see
# restart-consumers.sh) — so this stays root rather than switching back after install.
USER root

RUN apk add --no-cache docker-cli

COPY entrypoint.sh /entrypoint.sh
COPY restart-consumers.sh /restart-consumers.sh
RUN chmod +x /entrypoint.sh /restart-consumers.sh

ENTRYPOINT ["/entrypoint.sh"]
