import os
import importlib.util

# To resolve the namespace collision between the config/ directory package and the root config.py file,
# we dynamically load the root config.py module and export all its attributes into this package namespace.
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_py_path = os.path.join(parent_dir, "config.py")

if os.path.exists(config_py_path):
    spec = importlib.util.spec_from_file_location("root_config", config_py_path)
    if spec and spec.loader:
        root_config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(root_config)
        for attr in dir(root_config):
            if not attr.startswith("__"):
                globals()[attr] = getattr(root_config, attr)
