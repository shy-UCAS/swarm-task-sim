<!-- activate-conda-env:begin -->
## Project Python environment

Read `.conda-env` from this project root before running Python or installing packages.
The file contains this project's Conda environment name, not a global default.
Use `conda run -n <name> --no-capture-output python ...` and
`conda run -n <name> --no-capture-output python -m pip ...`.
Resolve the configuration before changing the command's working directory.
Never fall back to a skills installation directory or another project's environment.
If the file is missing, empty, or names an environment unavailable on this machine,
list local environments and ask the user to choose before environment-dependent work.
Do not silently switch to base or install into another interpreter.
<!-- activate-conda-env:end -->
