import os
import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import StreamStudioWindow


def main():
    lang = os.environ.get("MEDIAHUB_APP_LANG", "es")
    for arg in sys.argv[1:]:
        if arg.startswith("--lang="):
            lang = arg.split("=", 1)[1].strip() or "es"

    app = QApplication(sys.argv)
    window = StreamStudioWindow(lang=lang)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
