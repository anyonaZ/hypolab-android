import sys

from ideaweb.app import main

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(port, open_browser="--open" in sys.argv)
