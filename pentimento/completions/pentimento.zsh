#compdef pentimento

_pentimento() {
  local -a args
  args=("${words[@]:1:$((CURRENT - 1))}")
  local -a lines
  lines=("${(@f)$(pentimento __complete "${args[@]}")}")
  local -a descs
  local line value desc
  for line in "${lines[@]}"; do
    [[ -z "$line" ]] && continue
    value="${line%%$'\t'*}"
    if [[ "$line" == *$'\t'* ]]; then
      desc="${line#*$'\t'}"
    else
      desc="$value"
    fi
    descs+=("$value:$desc")
  done
  _describe 'pentimento' descs
}

# Autoloading this file (from fpath) only defines the function above; when
# the autoloader's own call *is* that first call, run it for real.
if [[ "$funcstack[1]" == "_pentimento" ]]; then
  _pentimento "$@"
fi
compdef _pentimento pentimento
