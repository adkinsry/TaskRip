"""Entry point for PyInstaller builds.

PyInstaller runs its target script as __main__, which breaks relative
imports inside the taskmanager package. This thin launcher imports the
package properly so relative imports resolve, then calls main().

For normal development, use `python -m taskmanager.main` or `./run.sh`.
"""

from taskmanager.main import main

if __name__ == "__main__":
    main()
