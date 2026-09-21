// OAuth2 PKCE login against the same Hydra instance and login-consent app client-admin
// already uses — this app logs into the one shared admin identity, not its own per-user
// account. login-consent stamps ext.role=admin onto every token it issues, regardless of
// which OAuth2 client drove the login, so registering a distinct client id here (see
// scripts/register-hydra-mobile-client.sh) is all that's needed to get the same admin
// authority client-admin already has.
import "package:flutter_appauth/flutter_appauth.dart";

const String _clientId = "whale-sightings-mobile";
const String _issuer = "https://auth.dev.whale-auth.org:4444";
const String _redirectUrl =
    "com.andyfox.whalesightings.clientmobile:/oauth2redirect";
const String _audience = "https://api.dev.wombat-sightings.org:8000";

final FlutterAppAuth _appAuth = FlutterAppAuth();

// In-memory only, no persistence — matches client-admin/app.js's own `accessToken` variable.
// A restart just means one more (fast, no-form-shown) round trip through Hydra, since its own
// remembered-login session already avoids repeated password entry within LOGIN_REMEMBER_SECONDS.
String? accessToken;

Future<void> login() async {
  final result = await _appAuth.authorizeAndExchangeCode(
    AuthorizationTokenRequest(
      _clientId,
      _redirectUrl,
      issuer: _issuer,
      scopes: ["openid"],
      additionalParameters: {"audience": _audience},
    ),
  );
  accessToken = result.accessToken;
}
