from dstack.core.config import BackendConfig, get_dstack_dir


class LocalConfig(BackendConfig):
    def __init__(self):
        self.path = get_dstack_dir()
