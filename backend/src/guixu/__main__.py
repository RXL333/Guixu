import os
import sys

from guixu.main import main

exit_code = main()
# pythonnet/WinForms may leave CLR-owned threads alive after webview.start has
# returned. At this point main() has already stopped uvicorn, closed the DB and
# released the single-instance lock; a frozen process must not linger invisibly.
if getattr(sys, "frozen", False):
    os._exit(exit_code)
raise SystemExit(exit_code)
