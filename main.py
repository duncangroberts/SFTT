from gui import App
from db import create_database

if __name__ == "__main__":
    create_database()
    app = App()
    app.mainloop()
