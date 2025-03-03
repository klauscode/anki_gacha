# -*- coding: utf-8 -*-
"""
Husbando Gacha Anki Addon
A gacha game addon for Anki that rewards you with husbando cards for studying,
now enhanced with gamified features like daily rewards, per-buddy leveling, fusion,
a shop, animations, limited events, mini-games, and stats.
"""

import os
import random
import json
import shutil
import base64
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, date

from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo, tooltip
from anki.hooks import wrap
from anki.cards import Card
from aqt.reviewer import Reviewer
from aqt.gui_hooks import reviewer_will_answer_card, reviewer_did_answer_card

# Constants
ADDON_NAME = "Husbando Gacha"
CONFIG_FILE = "husbando_gacha_config.json"
COLLECTION_FILE = "husbando_collection.json"
DEFAULT_PULL_COST = 50
DEFAULT_REWARDS = {
    "newCard": 1,          # Points for learning a new card
    "reviewCorrect": 1,      # Points for correct review
    "reviewHard": 1,         # Points for 'hard' on a review
    "reviewWrong": 0,        # Points for incorrect review
    "streak": {              # Bonus points for streaks
        "5": 5,
        "10": 10,
        "25": 25,
        "50": 50,
        "100": 100
    }
}
RARITIES = {
    "common": {"chance": 0.60, "color": "#A0A0A0"},
    "rare": {"chance": 0.30, "color": "#4169E1"},
    "epic": {"chance": 0.08, "color": "#9932CC"},
    "legendary": {"chance": 0.02, "color": "#FFD700"}
}


# Global variables
husbando_folder = ""
husbando_images = []
user_points = 0
current_streak = 0
collection = {}
config = {}
current_husbando = None
show_during_review = True

# NEW: Additional globals for daily rewards, achievements, and shop inventory
login_streak = 0
last_login_date = ""
achievements = {}   # e.g., {"first_pull": True, ...}
inventory = {}      # For items like upgrade materials or shop tickets

# -------------------------------
# Data loading & saving functions
# -------------------------------


def open_zoom_dialog(image_path):
    """Open a dialog displaying a larger version of the image."""
    if not os.path.exists(image_path):
        tooltip(f"Image not found: {image_path}")
        return
    dialog = QDialog(mw)
    dialog.setWindowTitle("Zoomed Image")
    dialog.setMinimumSize(600, 600)
    
    layout = QVBoxLayout()
    dialog.setLayout(layout)
    
    # Use a scroll area in case the image is larger than the dialog
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    layout.addWidget(scroll_area)
    
    content = QWidget()
    scroll_area.setWidget(content)
    content_layout = QVBoxLayout()
    content.setLayout(content_layout)
    
    image_label = QLabel()
    pixmap = QPixmap(image_path)
    image_label.setPixmap(pixmap)
    image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    content_layout.addWidget(image_label)
    
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.accept)
    content_layout.addWidget(close_btn)
    
    dialog.exec()



def load_addon_data():
    """Load addon configuration and user collection data."""
    global config, user_points, collection, husbando_folder, show_during_review
    global login_streak, last_login_date, achievements, inventory
    
    addon_dir = get_addon_dir()
    config_path = os.path.join(addon_dir, CONFIG_FILE)
    collection_path = os.path.join(addon_dir, COLLECTION_FILE)
    
    # Load or create config
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        config = {
            "pullCost": DEFAULT_PULL_COST,
            "rewards": DEFAULT_REWARDS,
            "husbandoFolder": "",
            "rarities": RARITIES,
            "showDuringReview": True,
            # Additional config options (e.g., theme) can be added here.
        }
        save_config()
    
    # Load or create collection with additional gamification data
    if os.path.exists(collection_path):
        with open(collection_path, 'r', encoding='utf-8') as f:
            collection_data = json.load(f)
            collection = collection_data.get("collection", {})
            user_points = collection_data.get("points", 0)
            login_streak = collection_data.get("login_streak", 0)
            last_login_date = collection_data.get("last_login_date", "")
            achievements = collection_data.get("achievements", {})
            inventory = collection_data.get("inventory", {})
    else:
        collection = {}
        user_points = 0
        login_streak = 0
        last_login_date = ""
        achievements = {}
        inventory = {}
        save_collection()
    
    husbando_folder = config.get("husbandoFolder", "")
    show_during_review = config.get("showDuringReview", True)
    
    if husbando_folder:
        load_husbando_images()

def get_addon_dir():
    """Get the addon directory path."""
    return os.path.dirname(os.path.abspath(__file__))

def save_config():
    """Save the addon configuration to disk."""
    config_path = os.path.join(get_addon_dir(), CONFIG_FILE)
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)

def save_collection():
    """Save the user's husbando collection, points, and gamification data to disk."""
    collection_path = os.path.join(get_addon_dir(), COLLECTION_FILE)
    with open(collection_path, 'w', encoding='utf-8') as f:
        collection_data = {
            "collection": collection,
            "points": user_points,
            "login_streak": login_streak,
            "last_login_date": last_login_date,
            "achievements": achievements,
            "inventory": inventory
        }
        json.dump(collection_data, f, indent=2)

def load_husbando_images():
    """Load husbando images from the specified folder."""
    global husbando_images
    
    if not husbando_folder or not os.path.exists(husbando_folder):
        husbando_images = []
        return
    
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif']
    husbando_images = []
    
    for file in os.listdir(husbando_folder):
        file_path = os.path.join(husbando_folder, file)
        if os.path.isfile(file_path) and os.path.splitext(file)[1].lower() in valid_extensions:
            husbando_images.append(file)

# -------------------------------
# Existing Gacha & Points Functions
# -------------------------------
def get_random_rarity() -> str:
    """Select a random rarity based on specified chances."""
    rarities = config.get("rarities", RARITIES)
    r = random.random()
    cumulative = 0
    for rarity, data in rarities.items():
        cumulative += data["chance"]
        if r <= cumulative:
            return rarity
    return "common"

def get_husbando_by_rarity(rarity: str) -> Optional[str]:
    """Get a random husbando image filtered by rarity."""
    if not husbando_images:
        return None
    return random.choice(husbando_images)

def get_random_husbando() -> Optional[Tuple[str, str, str]]:
    """Get a random husbando from the collection or a placeholder if collection is empty."""
    global collection, husbando_images
    if not husbando_images:
        return None
    if collection:
        husbando_file = random.choice(list(collection.keys()))
        rarity = collection[husbando_file]["rarity"]
        return (husbando_file, rarity, os.path.join(husbando_folder, husbando_file))
    husbando_file = random.choice(husbando_images)
    return (husbando_file, "common", os.path.join(husbando_folder, husbando_file))

def add_points(amount: int):
    """Add points to the user's balance."""
    global user_points
    user_points += amount
    save_collection()
    tooltip(f"+{amount} points! Total: {user_points}")

# -------------------------------
# NEW: Daily Rewards & Login Streaks
# -------------------------------
def check_daily_reward():
    """Check daily login and award bonus points for consecutive logins."""
    global last_login_date, login_streak, user_points
    today = date.today().isoformat()
    if last_login_date != today:
        if last_login_date:
            last_date = datetime.fromisoformat(last_login_date).date()
            if (date.today() - last_date).days == 1:
                login_streak += 1
            else:
                login_streak = 1
        else:
            login_streak = 1
        last_login_date = today
        base_reward = 50
        bonus = (login_streak - 1) * 10
        add_points(base_reward + bonus)
        tooltip(f"Daily reward: +{base_reward + bonus} points! (Streak: {login_streak} days)")
        save_collection()

# -------------------------------
# NEW: Buddy XP & Level (per current husbando)
# -------------------------------
def add_buddy_xp(amount: int):
    """Add XP to the current buddy and level up if threshold is reached."""
    global current_husbando, collection
    if current_husbando:
        husbando_file, _, _ = current_husbando
        if husbando_file not in collection:
            return
        # Initialize xp and level if not present
        collection[husbando_file].setdefault("xp", 0)
        collection[husbando_file].setdefault("level", 1)
        collection[husbando_file]["xp"] += amount
        xp_to_next = collection[husbando_file]["level"] * 100
        if collection[husbando_file]["xp"] >= xp_to_next:
            collection[husbando_file]["xp"] -= xp_to_next
            collection[husbando_file]["level"] += 1
            tooltip(f"{os.path.splitext(husbando_file)[0]} leveled up to Level {collection[husbando_file]['level']}!")
            add_points(50)  # bonus points for buddy leveling up
        save_collection()

# -------------------------------
# NEW: Achievements & Challenges
# -------------------------------
def check_achievements():
    """Check and unlock achievements based on current progress."""
    global achievements, collection
    if "first_pull" not in achievements and collection:
        achievements["first_pull"] = True
        add_points(100)
        tooltip("Achievement unlocked: First Pull! +100 points")
        save_collection()
    # Additional achievement checks can be added here.

# -------------------------------
# NEW: Fusion & Upgrades
# -------------------------------
def fuse_husbando(husbando_file: str):
    """Fuse 3 duplicates of a husbando to upgrade its rarity."""
    global collection
    if husbando_file in collection and collection[husbando_file]["count"] >= 3:
        collection[husbando_file]["count"] -= 3
        rarity_order = ["common", "rare", "epic", "legendary"]
        current_rarity = collection[husbando_file]["rarity"]
        if current_rarity in rarity_order and rarity_order.index(current_rarity) < len(rarity_order) - 1:
            new_rarity = rarity_order[rarity_order.index(current_rarity) + 1]
            collection[husbando_file]["rarity"] = new_rarity
            tooltip(f"Fusion successful! {husbando_file} is now {new_rarity.upper()}")
        else:
            tooltip("Already at highest rarity!")
        save_collection()
    else:
        tooltip("Not enough copies to fuse!")

# -------------------------------
# NEW: Gacha Pull (with Animated Pulling System)
# -------------------------------
def pull_husbando() -> Optional[Tuple[str, str, str]]:
    """Pull a random husbando card."""
    global user_points, current_husbando, collection
    pull_cost = config.get("pullCost", DEFAULT_PULL_COST)
    if user_points < pull_cost:
        tooltip(f"Not enough points! You need {pull_cost} points.")
        return None
    if not husbando_images:
        tooltip("No husbando images found!")
        return None
    user_points -= pull_cost
    save_collection()
    rarity = get_random_rarity()
    husbando_file = get_husbando_by_rarity(rarity)
    if not husbando_file:
        return None
    # If new, initialize xp and level for this husbando
    if husbando_file not in collection:
        collection[husbando_file] = {
            "count": 0,
            "rarity": rarity,
            "favorite": False,
            "xp": 0,
            "level": 1,
            "hp": 100  # initialize HP at 100
        }
    collection[husbando_file]["count"] += 1
    save_collection()
    current_husbando = (husbando_file, rarity, os.path.join(husbando_folder, husbando_file))
    # Award XP for pulling (to the current buddy)
    add_buddy_xp(5)
    check_achievements()
    # Stub for events (if active)
    if get_active_event():
        tooltip(f"Event bonus active: Enjoy the {get_active_event()}!")
    return current_husbando

def open_pull_dialog():
    """Open the dialog for pulling husbando cards with an animation."""
    result = pull_husbando()
    if not result:
        return

    # Show pull animation dialog
    anim_dialog = QDialog(mw)
    anim_dialog.setWindowTitle("Pulling Husbando...")
    anim_dialog.setMinimumSize(300, 200)
    anim_layout = QVBoxLayout()
    anim_dialog.setLayout(anim_layout)
    anim_label = QLabel("<h2>Drawing your husbando...</h2>")
    anim_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    anim_layout.addWidget(anim_label)
    anim_dialog.show()
    
    QTimer.singleShot(1500, lambda: finish_pull_dialog(anim_dialog, result))

def finish_pull_dialog(anim_dialog, result):
    """Finish the pull animation and show the result."""
    anim_dialog.accept()
    husbando_file, rarity, file_path = result
    dialog = QDialog(mw)
    dialog.setWindowTitle("Husbando Pull Result")
    dialog.setMinimumSize(400, 500)
    layout = QVBoxLayout()
    dialog.setLayout(layout)
    
    rarity_color = config.get("rarities", RARITIES)[rarity]["color"]
    rarity_label = QLabel(f"<h1 style='color:{rarity_color};text-align:center;'>{rarity.upper()}</h1>")
    rarity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(rarity_label)
    
    image_label = QLabel()
    pixmap = QPixmap(file_path)
    pixmap = pixmap.scaled(300, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    image_label.setPixmap(pixmap)
    image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(image_label)
    
    name_label = QLabel(os.path.splitext(husbando_file)[0])
    name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(name_label)
    
    count = collection[husbando_file]["count"]
    count_text = "First pull!" if count == 1 else f"You now have {count} copies!"
    info_label = QLabel(count_text)
    info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(info_label)
    
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.accept)
    layout.addWidget(close_btn)
    pull_again = QPushButton("Again")
    pull_again.clicked.connect(dialog.accept)
    pull_again.clicked.connect(open_pull_dialog)
    layout.addWidget(pull_again)
    
    dialog.exec()

# -------------------------------
# NEW: Limited Time Events (Stub)
# -------------------------------
def get_active_event():
    """Return the name of an active event if any."""
    today = date.today()
    # Example event: Holiday Event from Dec 20 to Dec 31
    event_start = date(today.year, 12, 20)
    event_end = date(today.year, 12, 31)
    if event_start <= today <= event_end:
        return "Holiday Event"
    return None

# -------------------------------
# NEW: Lucky Rolls & Mini-Games
# -------------------------------
def open_lucky_roll_dialog():
    """Open a mini-game for a lucky roll."""
    global user_points
    dialog = QDialog(mw)
    dialog.setWindowTitle("Lucky Roll")
    dialog.setMinimumSize(300, 200)
    layout = QVBoxLayout()
    dialog.setLayout(layout)
    cost = 20
    if user_points < cost:
        tooltip("Not enough points for Lucky Roll!")
        return
    user_points -= cost
    save_collection()
    roll_label = QLabel("<h2>Spinning the wheel...</h2>")
    roll_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(roll_label)
    
    outcomes = [("Jackpot", 100), ("Bonus XP", 50), ("Small Prize", 10), ("Miss", 0)]
    def reveal_outcome():
        outcome, reward = random.choice(outcomes)
        if outcome == "Bonus XP":
            add_buddy_xp(reward)
        elif reward > 0:
            add_points(reward)
        result_text = f"You got {outcome}! Reward: {'+'+str(reward) if reward > 0 else 'No reward'}"
        roll_label.setText(result_text)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
    QTimer.singleShot(1500, reveal_outcome)
    dialog.exec()

# -------------------------------
# NEW: Shop & In-Game Currency
# -------------------------------
def shop_buy_action(item, points_label):
    """Perform the purchase for a shop item."""
    global user_points, inventory, config
    if user_points < item["cost"]:
        tooltip("Not enough points!")
        return
    user_points -= item["cost"]
    if item["action"] == "rare_pull":
        config["shop_bonus"] = "rare_pull"  # flag for next pull bonus
        tooltip("Guaranteed Rare Pull activated for your next pull!")
    elif item["action"] == "free_pull":
        add_points(config.get("pullCost", DEFAULT_PULL_COST))  # refund pull cost
        tooltip("Free Pull activated!")
    elif item["action"] == "night_theme":
        config["theme"] = "night"
        tooltip("Night Theme unlocked! (Apply in settings)")
    save_collection()
    points_label.setText(f"Current Points: {user_points}")

def open_shop_dialog():
    """Open the in-game shop where you can spend points on bonuses and cosmetics."""
    global user_points, inventory
    dialog = QDialog(mw)
    dialog.setWindowTitle("Husbando Shop")
    dialog.setMinimumSize(400, 300)
    layout = QVBoxLayout()
    dialog.setLayout(layout)
    points_label = QLabel(f"Current Points: {user_points}")
    layout.addWidget(points_label)
    
    # Define shop items
    shop_items = [
        {"name": "Guaranteed Rare Pull", "cost": 200, "description": "Your next pull is guaranteed to be at least Rare.", "action": "rare_pull"},
        {"name": "Free Pull Ticket", "cost": 150, "description": "Perform an extra free pull.", "action": "free_pull"},
        {"name": "Night Theme", "cost": 100, "description": "Unlock a new night mode for your addon.", "action": "night_theme"}
    ]
    for item in shop_items:
        item_widget = QWidget()
        item_layout = QHBoxLayout()
        item_widget.setLayout(item_layout)
        label = QLabel(f"{item['name']} - {item['description']} (Cost: {item['cost']})")
        item_layout.addWidget(label)
        buy_btn = QPushButton("Buy")
        # Use lambda to pass the current item and points_label to shop_buy_action
        buy_btn.clicked.connect(lambda _, i=item: shop_buy_action(i, points_label))
        item_layout.addWidget(buy_btn)
        layout.addWidget(item_widget)
    
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.accept)
    layout.addWidget(close_btn)
    dialog.exec()

# -------------------------------
# NEW: Social & Stats Features
# -------------------------------
def open_stats_dialog():
    """Display user statistics and progress for your current buddy."""
    dialog = QDialog(mw)
    dialog.setWindowTitle("Your Stats")
    dialog.setMinimumSize(400, 300)
    layout = QVBoxLayout()
    dialog.setLayout(layout)
    
    buddy_info = ""
    if current_husbando:
        husbando_file, _, _ = current_husbando
        if husbando_file in collection:
            buddy = collection[husbando_file]
            xp = buddy.get("xp", 0)
            level = buddy.get("level", 1)
            xp_to_next = level * 100
            buddy_info = f"<p><b>Current Buddy:</b> {os.path.splitext(husbando_file)[0]}<br>Level: {level} (XP: {xp}/{xp_to_next})</p>"
    
    stats_text = f"""
    <h3>Statistics</h3>
    <p>Points: {user_points}</p>
    {buddy_info}
    <p>Total Pulls: {sum([data['count'] for data in collection.values()])}</p>
    """
    stats_label = QLabel(stats_text)
    stats_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    layout.addWidget(stats_label)
    
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.accept)
    layout.addWidget(close_btn)
    dialog.exec()

# -------------------------------
# Existing Anki Hooks and UI Functions
# -------------------------------
def on_card_answered(reviewer, card, ease):
    """
    New reward scheme based on answer ease:
    - Again (1):    -5 HP,   0 XP,  0 points
    - Hard (2):     -2 HP,  +2 XP, +2 points
    - Good (3):    +1 HP,  +5 XP, +5 points
    - Easy (4):   +10 HP, +10 XP, +10 points
    """
    global current_husbando  # Declare current_husbando as global

    # Make sure ease is a number, not a Card object
    ease_value = int(ease) if isinstance(ease, (int, str)) else 0
    
    reward_scheme = {
        1: {"hp": -5, "xp": 0, "points": 0},
        2: {"hp": -2, "xp": 2, "points": 2},
        3: {"hp": 1,  "xp": 5, "points": 5},
        4: {"hp": 10, "xp": 10, "points": 10},
    }
    
    reward = reward_scheme.get(ease_value, {"hp": 0, "xp": 0, "points": 0})
    tooltip(f"Card answered with ease {ease_value}")
    
    # Update current husbando's stats if available
    if current_husbando:
        husbando_file, _, _ = current_husbando
        if husbando_file in collection:
            husbando = collection[husbando_file]
            # Update HP and cap between 0 and 100
            current_hp = husbando.get("hp", 0)
            new_hp = current_hp + reward["hp"]
            husbando["hp"] = max(0, min(new_hp, 100))  # Ensure HP stays between 0-100
            
            # Check if husbando's HP has reached 0
            if husbando["hp"] == 0:
                del collection[husbando_file]
                tooltip(f"{os.path.splitext(husbando_file)[0]} has died and has been removed from your collection.")
                current_husbando = None  # Clear current husbando if it dies
            else:
                # Update XP
                husbando["xp"] = husbando.get("xp", 0) + reward["xp"]
                xp_to_next = husbando["level"] * 100
                if husbando["xp"] >= xp_to_next:
                    husbando["xp"] -= xp_to_next
                    husbando["level"] += 1
                    tooltip(f"{os.path.splitext(husbando_file)[0]} leveled up to Level {husbando['level']}!")
                    add_points(50)  # bonus points for leveling up
                
                collection[husbando_file] = husbando
                tooltip(f"{os.path.splitext(husbando_file)[0]} stats: HP {husbando['hp']}, XP {husbando['xp']}")
            
            save_collection()
    
    # Award user points (gacha currency)
    add_points(reward["points"])

def setup_menu():
    """Set up the addon menu in Anki."""
    menu = QMenu(ADDON_NAME, mw.form.menubar)
    mw.form.menubar.addMenu(menu)
    
    pull_action = QAction("Pull Husbando", mw)
    pull_action.triggered.connect(open_pull_dialog)
    menu.addAction(pull_action)
    
    collection_action = QAction("View Collection", mw)
    collection_action.triggered.connect(open_collection_dialog)
    menu.addAction(collection_action)
    
    settings_action = QAction("Settings", mw)
    settings_action.triggered.connect(open_settings_dialog)
    menu.addAction(settings_action)
    
    # NEW: Add Shop, Lucky Roll, and Stats actions
    shop_action = QAction("Shop", mw)
    shop_action.triggered.connect(open_shop_dialog)
    menu.addAction(shop_action)
    
    lucky_roll_action = QAction("Lucky Roll", mw)
    lucky_roll_action.triggered.connect(open_lucky_roll_dialog)
    menu.addAction(lucky_roll_action)
    
    stats_action = QAction("Stats", mw)
    stats_action.triggered.connect(open_stats_dialog)
    menu.addAction(stats_action)

def open_collection_dialog():
    """Open the dialog to view husbando collection with refresh, zoom, and HP display."""
    if not collection:
        showInfo("Your collection is empty! Study to earn points and pull husbandos.")
        return
    
    dialog = QDialog(mw)
    dialog.setWindowTitle("Husbando Collection")
    dialog.setMinimumSize(800, 600)
    
    layout = QVBoxLayout()
    dialog.setLayout(layout)
    
    points_label = QLabel(f"<h3>Current Points: {user_points}</h3>")
    layout.addWidget(points_label)
    
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_content = QWidget()
    grid_layout = QGridLayout(scroll_content)
    
    # Sort the collection by rarity order then name
    sorted_collection = sorted(
        collection.items(),
        key=lambda x: (
            list(config.get("rarities", RARITIES).keys()).index(x[1]["rarity"]),
            x[0]
        )
    )
    
    row, col = 0, 0
    max_cols = 4
    for husbando_file, data in sorted_collection:
        card_widget = QWidget()
        card_layout = QVBoxLayout()
        card_widget.setLayout(card_layout)
        image_path = os.path.join(husbando_folder, husbando_file)
        
        if os.path.exists(image_path):
            image_label = QLabel()
            pixmap = QPixmap(image_path)
            pixmap = pixmap.scaled(150, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            image_label.setPixmap(pixmap)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(image_label)
            
            # Add a Zoom button for the image
            zoom_btn = QPushButton("Zoom")
            zoom_btn.clicked.connect(lambda checked, path=image_path: open_zoom_dialog(path))
            card_layout.addWidget(zoom_btn)
        
        rarity_color = config.get("rarities", RARITIES)[data["rarity"]]["color"]
        name_label = QLabel(f"<span style='color:{rarity_color};'>{os.path.splitext(husbando_file)[0]}</span>")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(name_label)
        
        count_label = QLabel(f"Copies: {data['count']}")
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(count_label)
        
        # Display the current HP of the husbando
        current_hp = data.get("hp", 100)
        hp_label = QLabel(f"HP: {current_hp}")
        hp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(hp_label)
        
        current_btn = QPushButton("Set as Current")
        current_btn.clicked.connect(lambda checked, file=husbando_file, rar=data["rarity"]: set_current_husbando(file, rar))
        card_layout.addWidget(current_btn)
        
        # Fuse button to upgrade card rarity if enough copies
        fuse_btn = QPushButton("Fuse")
        fuse_btn.clicked.connect(lambda checked, file=husbando_file: fuse_husbando(file))
        card_layout.addWidget(fuse_btn)
        
        grid_layout.addWidget(card_widget, row, col)
        col += 1
        if col >= max_cols:
            col = 0
            row += 1
    
    scroll_area.setWidget(scroll_content)
    layout.addWidget(scroll_area)
    
    # Refresh button to update the collection view
    refresh_btn = QPushButton("Refresh Collection")
    refresh_btn.clicked.connect(lambda: (dialog.accept(), open_collection_dialog()))
    layout.addWidget(refresh_btn)
    
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.accept)
    layout.addWidget(close_btn)
    
    dialog.exec()


def set_current_husbando(husbando_file, rarity):
    """Set a husbando as the current displayed one."""
    global current_husbando
    file_path = os.path.join(husbando_folder, husbando_file)
    if os.path.exists(file_path):
        current_husbando = (husbando_file, rarity, file_path)
        tooltip(f"Set {os.path.splitext(husbando_file)[0]} as current husbando!")

def open_settings_dialog():
    """Open settings dialog."""
    global husbando_folder, show_during_review
    dialog = QDialog(mw)
    dialog.setWindowTitle("Husbando Gacha Settings")
    dialog.setMinimumSize(400, 300)
    layout = QVBoxLayout()
    dialog.setLayout(layout)
    
    folder_label = QLabel("Husbando Images Folder:")
    layout.addWidget(folder_label)
    
    folder_layout = QHBoxLayout()
    folder_edit = QLineEdit(husbando_folder)
    folder_layout.addWidget(folder_edit)
    
    folder_btn = QPushButton("Browse...")
    folder_btn.clicked.connect(lambda: browse_folder(folder_edit))
    folder_layout.addWidget(folder_btn)
    layout.addLayout(folder_layout)
    
    show_review_check = QCheckBox("Show husbando during review")
    show_review_check.setChecked(show_during_review)
    layout.addWidget(show_review_check)
    
    cost_layout = QHBoxLayout()
    cost_label = QLabel("Points per Pull:")
    cost_layout.addWidget(cost_label)
    
    cost_spin = QSpinBox()
    cost_spin.setMinimum(1)
    cost_spin.setMaximum(1000)
    cost_spin.setValue(config.get("pullCost", DEFAULT_PULL_COST))
    cost_layout.addWidget(cost_spin)
    layout.addLayout(cost_layout)
    
    layout.addWidget(QLabel("<h3>Reward Points</h3>"))
    rewards = config.get("rewards", DEFAULT_REWARDS)
    reward_grid = QGridLayout()
    reward_grid.addWidget(QLabel("Correct answer:"), 0, 0)
    correct_spin = QSpinBox()
    correct_spin.setValue(rewards.get("reviewCorrect", 1))
    reward_grid.addWidget(correct_spin, 0, 1)
    reward_grid.addWidget(QLabel("Hard answer:"), 1, 0)
    hard_spin = QSpinBox()
    hard_spin.setValue(rewards.get("reviewHard", 1))
    reward_grid.addWidget(hard_spin, 1, 1)
    reward_grid.addWidget(QLabel("Wrong answer:"), 2, 0)
    wrong_spin = QSpinBox()
    wrong_spin.setValue(rewards.get("reviewWrong", 0))
    reward_grid.addWidget(wrong_spin, 2, 1)
    layout.addLayout(reward_grid)
    
    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    button_box.accepted.connect(lambda: save_settings(
        dialog,
        folder_edit.text(),
        cost_spin.value(),
        correct_spin.value(),
        hard_spin.value(),
        wrong_spin.value(),
        show_review_check.isChecked()
    ))
    button_box.rejected.connect(dialog.reject)
    layout.addWidget(button_box)
    
    dialog.exec()

def browse_folder(line_edit):
    """Open folder browser dialog."""
    folder = QFileDialog.getExistingDirectory(mw, "Select Husbando Images Folder", line_edit.text())
    if folder:
        line_edit.setText(folder)

def save_settings(dialog, folder, pull_cost, correct, hard, wrong, show_review):
    """Save settings and close dialog."""
    global husbando_folder, config, show_during_review
    config["husbandoFolder"] = folder
    config["pullCost"] = pull_cost
    config["showDuringReview"] = show_review
    config["rewards"]["reviewCorrect"] = correct
    config["rewards"]["reviewHard"] = hard
    config["rewards"]["reviewWrong"] = wrong
    save_config()
    husbando_folder = folder
    show_during_review = show_review
    load_husbando_images()
    dialog.accept()
    tooltip("Settings saved!")

def encode_image_to_base64(file_path):
    """Convert an image file to a Base64 string for embedding in HTML."""
    if os.path.exists(file_path):
        with open(file_path, "rb") as img_file:
            return f"data:image/png;base64,{base64.b64encode(img_file.read()).decode('utf-8')}"
    return ""

def append_husbando_to_qa(html, card, context):
    """Inject husbando display into the review HTML."""

    global current_husbando, show_during_review
    if not show_during_review or not current_husbando:
        return html

    # Build buddy info if available
    husbando_file, rarity, file_path = current_husbando
    if husbando_file in collection:
        buddy = collection[husbando_file]
        xp = buddy.get("xp", 0)
        level = buddy.get("level", 1)
        xp_to_next = level * 100
        hp = buddy.get("hp", 100)
        buddy_info = (f"<p><b>Current Buddy:</b> {os.path.splitext(husbando_file)[0]}<br>"
                      f"Level: {level} (XP: {xp}/{xp_to_next}) (HP: {hp}/100)</p>")
    else:
        buddy_info = ""

    if not os.path.exists(file_path):
        tooltip(f"Image file not found: {file_path}")
        return html
    
    image_src = encode_image_to_base64(file_path)
    title = os.path.splitext(husbando_file)[0]

    # Rarity style configuration
    rarity_styles = {
        "legendary": {
            "badge": "LEGENDARY",
            "badge_bg": "linear-gradient(45deg, #D97706, #F59E0B)",
            "badge_border": "#FCD34D",
            "container_border": "#F59E0B",
            "container_shadow": "rgba(245, 158, 11, 0.3)",
            "container_bg": "rgba(30, 27, 25, 0.95)",
            "box_shadow_color": "rgba(245, 158, 11, 0.3)"
        },
        "rare": {
            "badge": "RARE",
            "badge_bg": "linear-gradient(45deg, #1D4ED8, #3B82F6)",
            "badge_border": "#60A5FA",
            "container_border": "#3B82F6",
            "container_shadow": "rgba(59, 130, 246, 0.25)",
            "container_bg": "rgba(10, 20, 40, 0.95)",
            "box_shadow_color": "rgba(59, 130, 246, 0.3)"
        },
        "common": {
            "badge": "COMMON",
            "badge_bg": "linear-gradient(45deg, #4B5563, #6B7280)",
            "badge_border": "#9CA3AF",
            "container_border": "#6B7280",
            "container_shadow": "rgba(156, 163, 175, 0.1)",
            "container_bg": "rgba(40, 40, 40, 0.95)",
            "box_shadow_color": "rgba(0, 0, 0, 0.2)"
        },
        "epic": {
            "badge": "EPIC",
            "badge_bg": "linear-gradient(45deg, #6D28D9, #8B5CF6)",
            "badge_border": "#C084FC",
            "container_border": "#8B5CF6",
            "container_shadow": "rgba(147, 51, 234, 0.3)",
            "container_bg": "rgba(30, 0, 30, 0.95)",
            "box_shadow_color": "rgba(147, 51, 234, 0.3)"
        }
    }
    style = rarity_styles.get(rarity, rarity_styles["common"])

    # Unified HTML template with centered position
    husbando_html = f"""
<div style="
    position: fixed;
    top: 65%;
    left: 10%;
    transform: translate(-50%, -50%);
    z-index: 1000;
    text-align: center;
    background: {style['container_bg']};
    border-radius: 20px;
    padding: 20px;
    border: 2px solid {style['container_border']};
    box-shadow: 0 0 35px {style['container_shadow']};
    backdrop-filter: blur(12px);
    width: 250px;
    height: 525px;
    color: white;
    font-family: 'Arial', sans-serif;">
    
    <!-- Badge -->
    <div style="
         position: absolute;
         top: -15px;
         left: 50%;
         transform: translateX(-50%);
         background: {style['badge_bg']};
         padding: 6px 25px;
         border-radius: 25px;
         font-size: 0.9rem;
         font-weight: 700;
         letter-spacing: 2px;
         box-shadow: 0 4px 15px {style['box_shadow_color']};
         border: 1px solid {style['badge_border']};
         text-transform: uppercase;">
         {style['badge']}
    </div>
    
    <!-- Title -->
    <div style="
         color: #FDE68A;
         font-weight: 800;
         margin: 20px 0 15px 0;
         font-size: 1.4rem;
         text-transform: uppercase;
         letter-spacing: 2px;
         text-shadow: 0 0 12px rgba(251, 191, 36, 0.4);">
         {title}
    </div>
    
    <!-- Image Container -->
    <div style="
         border-radius: 12px;
         overflow: hidden;
         border: 2px solid {style['container_border']};
         box-shadow: 0 0 25px {style['container_shadow']};
         position: relative;
         width: 250px;
         height: 375px;">
         <img src="{image_src}" style="
              width: 100%;
              height: 100%;
              object-fit: cover;
              display: block;
              transition: transform 0.3s ease;">
         <div style="
              position: absolute;
              top: 0;
              left: 0;
              right: 0;
              bottom: 0;
              background: linear-gradient(45deg, rgba(30,27,25,0.1), rgba(245,158,11,0.05));">
         </div>
    </div>
    
    <!-- Info Text -->
    <div style="
         margin: 18px 0 10px 0;
         font-size: 0.95rem;
         color: #FCD34D;
         line-height: 1.5;
         padding: 0 12px;
         font-weight: 500;">
         {buddy_info}
    </div>
    
    <!-- Golden Sparkles -->
    <div style="
         position: absolute;
         top: 15%;
         left: -20px;
         width: 50px;
         height: 50px;
         background: radial-gradient(circle, rgba(255,215,0,0.6) 0%, transparent 70%);
         mix-blend-mode: overlay;
         transform: rotate(25deg);
         pointer-events: none;">
    </div>
    <div style="
         position: absolute;
         bottom: 25%;
         right: -20px;
         width: 40px;
         height: 40px;
         background: radial-gradient(circle, rgba(255,215,0,0.5) 0%, transparent 70%);
         mix-blend-mode: overlay;
         transform: rotate(-15deg);
         pointer-events: none;">
    </div>
</div>
"""
    return html + husbando_html

def handle_answer(reviewer, card, ease):
    tooltip("handle_answer was called!")  # Debug message
    on_card_answered(reviewer, card, ease)

# -------------------------------
# Main Initialization
# -------------------------------
def init():
    global current_husbando
    load_addon_data()
    check_daily_reward()  # Trigger daily reward check on startup
    setup_menu()
    if collection:
        current_husbando = get_random_husbando()
    from aqt import gui_hooks
    gui_hooks.card_will_show.append(append_husbando_to_qa)
    gui_hooks.reviewer_did_answer_card.append(handle_answer)
    gui_hooks.reviewer_did_answer_card.append(handle_answer)


init()


