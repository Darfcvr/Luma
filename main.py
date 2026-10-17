from gui.launcher import Launcher
from PySide6.QtWidgets import QApplication
import sys
if __name__=='__main__':
 app=QApplication(sys.argv);w=Launcher();w.show();sys.exit(app.exec())
