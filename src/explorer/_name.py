"""The application's name, in one place (docs/decisions/0003): renaming explorer is this file plus the few
absolute references listed in that decision. Everything the user sees derives from APP_NAME."""
APP_NAME = "explorer"                   # provisional
ENV_PREFIX = APP_NAME.upper() + "_"     # environment variables: EXPLORER_LOG, ...
