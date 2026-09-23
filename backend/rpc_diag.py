
"""Diagnose whether the installed modifyself has everything the RPC image
upload needs. Run:  python backend\\rpc_diag.py"""
import sys

print("=" * 56)
print(" Beyond RPC image-upload diagnostic")
print("=" * 56)
print("python:", sys.executable)

try:
    import modifyself
    print("modifyself version:", getattr(modifyself, "__version__", "unknown"))
except Exception as e:
    print("modifyself import FAILED:", repr(e))
    sys.exit(1)

ok = True

try:
    import wreq
    from wreq import Method
    print("wreq:               OK")
except Exception as e:
    ok = False
    print("wreq:               MISSING ->", repr(e))

try:
    from modifyself import Client
    c = Client(token="diagnostic", command_prefix=".", notifications=False)
    http = c._http
    checks = {
        "_http._get_client": hasattr(http, "_get_client"),
        "_http._spoofer":    hasattr(http, "_spoofer"),
        "_http.token":       hasattr(http, "token"),
    }
    sp = getattr(http, "_spoofer", None)
    for attr in ("get_headers", "profile", "build_number", "_launch_id",
                 "_launch_signature", "_heartbeat_session_id", "_app_state",
                 "_installation_id"):
        checks[f"spoofer.{attr}"] = hasattr(sp, attr)
    for k, v in checks.items():
        print(f"{k:24s}: {'OK' if v else 'MISSING'}")
        ok = ok and v
except Exception as e:
    ok = False
    print("client inspect failed:", repr(e))

print("-" * 56)
if ok:
    print("RESULT: this modifyself HAS everything the RPC upload needs.")
    print("If images still fail, paste the backend RPC error/traceback.")
else:
    print("RESULT: this modifyself is MISSING internals the upload needs.")
    print("You're on the wrong/older build. Install modifyself 0.5.1:")
    print('   python -m pip install --force-reinstall modifyself-0.5.1-py3-none-any.whl')
