class DRBDSync:
    LOG_PATH = '/var/log/kern.log'
    GREP_PATTHERN = 'Resync done'
    PYTHON_PATTERN = 'Resync done .* (\d+) K\/sec'
