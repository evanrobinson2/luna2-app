#### ISSUES


1. Lunabot is the admin, it's hardcoded in multiple files
2. Multiple files declare globals and constants, those should move to a config file of some kind
3. Keys like the director key should be stored in environment variables, not on disk
