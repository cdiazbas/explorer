"""The application's name, in one place: renaming explorer is this file plus the few absolute references
(pyproject's [project.scripts] and import-linter contracts, the tests, tools/; the package imports itself
relatively). Everything the user sees derives from APP_NAME."""
APP_NAME = "explorer"                   # provisional
ENV_PREFIX = APP_NAME.upper() + "_"     # environment variables: EXPLORER_LOG, ...
