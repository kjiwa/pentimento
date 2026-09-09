# demo

`fixture.sh` writes a synthetic plan corpus (used by `capture.sh` to
regenerate the README's sample output and by `record.sh` for the GIF, so
neither ever touches a real plans directory or leaks real project names).
Run `sh demo/capture.sh` to refresh the README samples and `sh demo/record.sh`
to regenerate `pentimento.gif` after changing output formatting.
