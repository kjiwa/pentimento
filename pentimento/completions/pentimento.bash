_pentimento() {
  local i last line prefix word words
  words=()
  for ((i = 1; i <= COMP_CWORD; i++)); do
    word="${COMP_WORDS[i]}"
    last=$((${#words[@]} - 1))
    if ((i > 1)) && [[ "$word" == = || "${words[last]}" == -*= ]]; then
      words[last]+="$word"
    else
      words+=("$word")
    fi
  done
  last=$((${#words[@]} - 1))
  prefix=""
  if [[ "${words[last]}" == -*=* ]]; then
    prefix="${words[last]%%=*}="
  fi
  COMPREPLY=()
  while IFS= read -r line; do
    line="${line%%$'\t'*}"
    COMPREPLY+=("${line#"$prefix"}")
  done < <(pentimento __complete "${words[@]}")
}
complete -F _pentimento pentimento
