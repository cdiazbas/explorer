"""explorer.core: the viewer's state and what it reads and shows. No Qt here (docs/decisions/0007): notices go to
plain functions, and when to process them and how to reach the main thread are given by whoever runs it (the UI, or
tests with a manual pump)."""
