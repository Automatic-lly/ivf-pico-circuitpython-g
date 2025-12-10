# MODE: master  # Change to "slave" to boot the slave firmware on next reset.
"""Entry point for CircuitPython.

This file dispatches to either ``master.py`` or ``slave.py`` at runtime. The
selection is controlled by the comment above: set ``MODE`` to ``master`` or
``slave`` to choose which board role should run when the Pico boots.
"""
import sys


def detect_mode(default: str = "master") -> str:
    """Read the first ``# MODE:`` line to decide which firmware to load."""
    try:
        with open("code.py", "r", encoding="utf-8") as self_file:
            for line in self_file:
                if line.startswith("# MODE:"):
                    return line.split(":", 1)[1].strip().lower().split()[0]
    except OSError:
        pass
    return default


MODE = detect_mode()

if MODE == "master":
    import master  # noqa: F401  (import triggers firmware execution)
elif MODE == "slave":
    import slave  # noqa: F401
else:
    sys.stderr.write(f"Unknown MODE '{MODE}'. Falling back to master.\n")
    import master  # noqa: F401
