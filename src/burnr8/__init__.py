from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("burnr8")
except PackageNotFoundError:
    __version__ = "0.7.0"  # Fallback for editable installs
