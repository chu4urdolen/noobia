# Deliberately stops on a failed load: a software return must mean every listed
# insmod completed successfully. This checks neither hardware binding nor USB.
lynx_load_checkpoint_modules() {
    while IFS= read -r module; do
        [ -n "$module" ] || continue
        log "CHECKPOINT_MODULE_BEGIN $module"
        if ! $BB insmod "/lib/modules/$module"; then
            log "CHECKPOINT_MODULE_FAILED $module"
            return 1
        fi
        log "CHECKPOINT_MODULE_OK $module"
    done < "$1"
}
