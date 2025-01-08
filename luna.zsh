#!/usr/bin/env zsh

# luna.zsh
# Gracefully start the 'luna.py' script by:
# 1) Changing to this script's directory.
# 2) Checking if we're in a virtual environment.
#    - If not, attempt to activate ./.venv.
# 3) Unalias 'python'.
# 4) Run 'python luna.py'.

# 1) Change to the script's directory so paths resolve properly:
cd "$(dirname "$0")"

# 2) Check if we are already in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
  # Not in a venv, so let's try to activate ./.venv
  if [[ -d "./.venv" && -f "./.venv/bin/activate" ]]; then
    echo "No virtual environment detected; activating .venv..."
    source .venv/bin/activate
  else
    echo "Error: No .venv found in $(pwd)."
    echo "Please create a virtual environment named '.venv' or activate it manually."
    exit 1
  fi
fi

# 3) Unalias python if there's any alias set
unalias python 2>/dev/null

# 4) Start Luna
echo "Starting Luna..."
python luna.py
