"""``python -m corpus`` delegates to the generator CLI."""

from .generate import main

if __name__ == "__main__":
    raise SystemExit(main())
