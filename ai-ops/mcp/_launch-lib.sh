# shellcheck shell=sh
# Shared by the MCP launchers. Usage:  launch_with_env <env-file> <command...>
#
#   env file has op:// references -> resolved by `op run` (1Password CLI required)
#   env file has plain values     -> exported directly (keep the file chmod 600)
#
# Works on macOS and Linux. On macOS, a 1Password service-account token stored in the
# login Keychain (service "op-service-account") lets op resolve refs headlessly.
launch_with_env() {
  _envf="$1"; shift
  [ -f "$_envf" ] || { echo "FATAL: $_envf not found - copy it from ${_envf}.example" >&2; exit 1; }
  if grep -q 'op://' "$_envf"; then
    command -v op >/dev/null 2>&1 || { echo "FATAL: $_envf uses op:// references but the 1Password CLI (op) is not on PATH" >&2; exit 1; }
    if [ -z "${OP_SERVICE_ACCOUNT_TOKEN:-}" ] && command -v security >/dev/null 2>&1; then
      # $(id -un), not $USER: MCP clients may spawn this with USER unset.
      if _T=$(security find-generic-password -a "$(id -un)" -s op-service-account -w 2>/dev/null) && [ -n "$_T" ]; then
        OP_SERVICE_ACCOUNT_TOKEN="$_T"; export OP_SERVICE_ACCOUNT_TOKEN
      fi
      unset _T
    fi
    exec op run --no-masking --env-file="$_envf" -- "$@"
  fi
  case "$(ls -l "$_envf" | cut -c5-10)" in
    ------) ;;
    *) echo "WARN: $_envf holds plain secrets and is readable by others - chmod 600 it" >&2;;
  esac
  set -a
  # shellcheck source=/dev/null
  . "$_envf"
  set +a
  exec "$@"
}
