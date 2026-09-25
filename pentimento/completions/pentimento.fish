function __pentimento_complete
    set -l cmd (commandline -opc)
    set -e cmd[1]
    pentimento __complete $cmd (commandline -ct)
end

complete -c pentimento -f -a '(__pentimento_complete)'
