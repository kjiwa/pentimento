# Regenerate with: sh demo/record.sh
Output demo/pentimento.gif

Require pentimento

Set Shell "bash"
Set FontSize 20
Set Width 1320
Set Height 800
Set Theme "Builtin Dark"
Set TypingSpeed 30ms

Hide
Type 'export HOME="$DEMO_HOME"; cd "$HOME/.claude/plans"; clear'
Enter
Show

# Act 1: the problem
Type "# plan files pile up; the names say nothing"
Enter
Sleep 1500ms

Type "ls *.md"
Enter
Sleep 2000ms

Type "pentimento backfill"
Enter
Sleep 1500ms

Type "pentimento list"
Enter
Sleep 2500ms

Type "clear"
Enter
Sleep 500ms

# Act 2: lineage
Type "# which plan replaced which, and pulling one thread out"
Enter
Sleep 1500ms

Type "pentimento tree"
Enter
Sleep 3000ms

Screenshot demo/pentimento-tree.png

Type "pentimento tree api-auth-rollout --ancestors"
Enter
Sleep 3000ms

Type "pentimento show api-auth-rollout"
Enter
Sleep 2500ms

Type "clear"
Enter
Sleep 500ms

# Act 3: drift
Type "# the corpus drifts; check catches it"
Enter
Sleep 1500ms

Type "pentimento check"
Enter
Sleep 2500ms

Type "clear"
Enter
Sleep 500ms

# Act 4: intent
Type "# status is derived; intent is yours to set"
Enter
Sleep 1500ms

Type "pentimento set billing-dunning-copy --intent active --add-tag followup"
Enter
Sleep 1500ms

Type "pentimento list --starred"
Enter
Sleep 3000ms
