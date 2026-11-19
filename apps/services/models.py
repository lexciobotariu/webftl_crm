"""Nothing left: Services (earlier Maintenance) was removed in 0.48.0.

The app stays installed only so its migrations can run: 0005 moves sites and
logins into the Vault (through ``vault.0002``) and drops its tables. It can be
deleted once every database has applied it.
"""
