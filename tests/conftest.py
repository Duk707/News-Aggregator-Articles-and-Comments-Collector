import os
import sys

# Ensure Anaconda Tcl/Tk library paths are set for Tkinter GUI test stability across full test runs
if hasattr(sys, 'prefix'):
    tcl_dir = os.path.join(sys.prefix, 'Library', 'lib', 'tcl8.6')
    tk_dir = os.path.join(sys.prefix, 'Library', 'lib', 'tk8.6')
    if os.path.exists(tcl_dir) and "TCL_LIBRARY" not in os.environ:
        os.environ["TCL_LIBRARY"] = tcl_dir
    if os.path.exists(tk_dir) and "TK_LIBRARY" not in os.environ:
        os.environ["TK_LIBRARY"] = tk_dir
