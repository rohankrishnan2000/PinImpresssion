#!/bin/zsh

# Double-click launcher for macOS. Keep this file beside launcher.py.
set -u

project_dir="${0:A:h}"
cd "$project_dir" || {
    print -u2 "Could not open the PinImpresssion folder: $project_dir"
    exit 1
}

choose_python() {
    if [[ -n "${PIN_IMPRESSION_PYTHON:-}" && -x "$PIN_IMPRESSION_PYTHON" ]]; then
        print -r -- "$PIN_IMPRESSION_PYTHON"
        return 0
    fi

    local candidate
    for candidate in \
        "$project_dir/.venv/bin/python" \
        "/opt/anaconda3/bin/python"
    do
        if [[ -x "$candidate" ]]; then
            print -r -- "$candidate"
            return 0
        fi
    done

    if command -v python >/dev/null 2>&1; then
        command -v python
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return 0
    fi
    return 1
}

python_executable="$(choose_python)" || {
    print -u2 "Python could not be found. Install Python 3, then try again."
    print "Press Return to close this window."
    read -r
    exit 1
}

if [[ ! -f "$project_dir/launcher.py" ]]; then
    print -u2 "launcher.py is missing from: $project_dir"
    print "Keep Start Pin Impression.command inside the PinImpresssion folder."
    print "Press Return to close this window."
    read -r
    exit 1
fi

export PYTHONUNBUFFERED=1
"$python_executable" "$project_dir/launcher.py"
launch_status=$?

if (( launch_status != 0 )); then
    print
    print -u2 "Pin Impression could not start (exit code $launch_status)."
    print -u2 "Python used: $python_executable"
    print -u2 "To install its dependencies, run this in Terminal:"
    print -u2 "  cd '$project_dir'"
    print -u2 "  '$python_executable' -m pip install -r requirements.txt"
    print
    print "Press Return to close this window."
    read -r
fi

exit "$launch_status"
