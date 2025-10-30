# One Night Ultimate Werewolf Card Dealer

This is a card-dealing program specifically designed for the board game "One Night Ultimate Werewolf," helping players quickly start the game and manage gameplay flow. The program provides both graphical and command-line interfaces, supporting core features such as role configuration, automatic card dealing, and nighttime phase guidance.

## 🧩 Features

- **Automatic Card Dealing**: Automatically assigns roles based on player count and selected difficulty mode
- **Nighttime Guidance**: Step-by-step prompts for each role’s nighttime actions
- **Role Management**: Supports custom role configurations and extensions
- **Dual Interface Support**: Provides both Tkinter and Qt graphical interfaces (Qt preferred)
- **Card Viewing**: Allows players to view and exchange their own role cards and central cards

## 📦 Project Structure

```
wolf/
├── core/               # Core card-dealing logic and game rules
├── gui/                # Graphical interface modules (Tkinter and Qt)
├── main.py             # Program entry point, automatically selects interface
├── resources/roles/    # Role image assets
├── resources/roles_config.json  # Role configuration file
└── tests/              # Unit tests
```

## 🛠️ Installation and Usage

### Dependencies

- Python 3.9 or higher
- tkinter (standard library, usually pre-installed)
- PyQt5 (optional, for Qt interface)

```bash
pip install pyqt5
```

### Running the Program

```bash
# Navigate to the project directory
cd wolf

# Run directly
python main.py
```

The program will attempt to launch the Qt interface first; if it fails, it will automatically fall back to the Tkinter interface.

## 🎮 Usage Instructions

1. **Select Roles**: Choose roles on the main interface or use the default configuration
2. **Start Game**: Click the "Start Game" button to automatically deal cards
3. **Night Phase**: Click "Night Mode" to step through each role's actions
4. **View and Exchange**: Players can click their own cards or central cards to view or swap them
5. **End Game**: View all cards at any time or restart the game

## 🧪 Unit Tests

The project includes basic unit tests to verify card-dealing logic and rule configurations:

```bash
# Run tests
python -m unittest tests/test_dealer.py
python -m unittest tests/test_rules.py
```

## 📄 Configuration Details

The role configuration file is located at `resources/roles_config.json` and supports custom roles and modes. Default rules cover base configurations for 4–9 players.

## 📚 Extensibility

- Add new roles by modifying `roles_config.json`
- Extend functionality by modifying logic in `core/werewolf_dealer.py`
- Customize interface styles or replace background images

## 📝 Contributions and Feedback

Contributions via Issues or Pull Requests are welcome. Please follow the project structure and coding conventions.

## 📄 License

This project is licensed under the MIT License. See the LICENSE file for details.