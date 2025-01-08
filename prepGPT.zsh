#!/usr/bin/env zsh
#
# combine_files_git.sh
#
# Description:
#   - Uses `git ls-files` to list all Git-tracked files.
#   - Filters for .py, .md, .csv, .json, .txt.
#   - Excludes .log, .env, and the output file.
#   - Appends file contents to combined.out with a header.
#   - Includes print statements at key steps for debugging.

OUTPUT_FILE="project-luna.md"

echo "[INFO] Starting script: $0"
echo "[INFO] Checking Git-tracked files..."

# Get a list of all Git-tracked files
git_files=( "${(@f)$(git ls-files)}" )

echo "[DEBUG] git ls-files returned ${#git_files[@]} files."

# Prepare an array for files we will actually combine
typeset -a FILELIST=()

echo "[INFO] Filtering files for valid extensions and exclusions..."
# Filter out unwanted extensions and skip the output file
for f in "${git_files[@]}"; do
  # Make sure it's a regular file on disk
  if [[ -f "$f" ]]; then
    case "$f" in
      *.py|*.md|*.csv|*.json|*.txt)
        # Exclude if .log or .env
        if [[ "$f" == *.log || "$f" == ".env" ]]; then
          echo "[DEBUG] Skipping '$f' because it's .log or .env."
          continue
        fi

        # Exclude the output file
        if [[ "$f" == "$OUTPUT_FILE" ]]; then
          echo "[DEBUG] Skipping '$f' because it matches OUTPUT_FILE."
          continue
        fi

        # If it passed all checks, add to FILELIST
        FILELIST+="$f"
        echo "[DEBUG] Added '$f' to FILELIST."
        ;;
      *)
        echo "[DEBUG] Skipping '$f' (extension not in .py, .md, .csv, .json, .txt)."
        ;;
    esac
  else
    echo "[DEBUG] Skipping '$f' because it's not a regular file (possibly deleted or a directory)."
  fi
done

echo "[INFO] Total files to combine: ${#FILELIST[@]}"

# Truncate or create the output file fresh
echo "[INFO] Truncating/creating '$OUTPUT_FILE'..."
# Force-remove the existing output file, ignoring "no such file" errors
rm -f "$OUTPUT_FILE" 2>/dev/null

# Recreate a fresh empty file
touch "$OUTPUT_FILE"


# Concatenate contents with headers
echo "[INFO] Combining files into '$OUTPUT_FILE'..."
for file in "${FILELIST[@]}"; do
  echo "[DEBUG] Writing contents of '$file' to '$OUTPUT_FILE'."
  echo "=== $file ===" >> "$OUTPUT_FILE"
  cat "$file" >> "$OUTPUT_FILE"
  echo >> "$OUTPUT_FILE"
done

echo "[INFO] Done. Output written to '$OUTPUT_FILE'."
