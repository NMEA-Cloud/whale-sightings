#!/bin/sh
# Invoked by `step ca renew --daemon --exec` (see entrypoint.sh) after every successful
# renewal. Restarts the 4 containers that read certs/localhost.pem or
# certs/localhost-key.pem once at startup and never watch the file afterward — uvicorn
# (service, login-consent) builds its SSLContext once at boot, Hydra's
# serve.tls.cert/key.path is read once at boot, and mosquitto loads certfile/keyfile once at
# boot with no reload wired up. (step-ca and dns never read the leaf cert; everything else
# only trusts certs/rootCA.pem, which a routine leaf renewal doesn't change.)
set -u

echo "[cert-renewer] Certificate renewed — restarting TLS-terminating containers..."
# One call, not split by project: docker restart handles each name independently and logs a
# harmless "No such container" for one that isn't running rather than aborting the rest.
docker restart \
  wombat-sightings-service-1 \
  wombat-sightings-mqtt-1 \
  whale-auth-hydra-1 \
  whale-auth-login-consent-1
echo "[cert-renewer] Restart complete."
