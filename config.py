# config.py
API_KEY = "raFD7dbj3RIl16CtJQykIzbyC0lC7nN6cQOk1yi4vCDfCV9hYAmxKsOjNTp2qOS2"
API_SECRET = "DLJ2rbAPcZ23STP0YaXrQGirHNN8sYMeuyzWZqVn4gI2MsdR10mfSk6cvMgOWono"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1357682737430921279/Eup3FuN-5kpLSni9leEas0BGkqx-voNMQcg6sKRlpbFDYKqFibGwkC3JhM-xo_yIj3jF"

DATA_FILES = {
    "safe": "safe_data.json",
    "mid": "mid_data.json",
    "agresif": "agresif_data.json"
}

CONFIGS = {
    "safe": {
        "LEFT": 15,
        "RIGHT": 15,
        "MANIPULATION_THRESHOLD": 0.01,
        "MAX_CANDLES": 15,
        "CONSECUTIVE_CANDLES": 4,
        "MIN_CANDLES_FOR_SECOND_CONDITION": 20,
        "MAX_CANDLES_FOR_SECOND_CONDITION": 25,
        "RISK_REWARD_RATIO": 1.5,
        "INITIAL_BALANCE": 10000,
        "MAX_RISK": 0.01,
        "RISK_TYPE": "fixed",
    },
    "mid": {
        "LEFT": 15,
        "RIGHT": 20,
        "MANIPULATION_THRESHOLD": 0.005,
        "MAX_CANDLES": 15,
        "CONSECUTIVE_CANDLES": 4,
        "MIN_CANDLES_FOR_SECOND_CONDITION": 20,
        "MAX_CANDLES_FOR_SECOND_CONDITION": 25,
        "RISK_REWARD_RATIO": 1.5,
        "INITIAL_BALANCE": 10000,
        "MAX_RISK": 0.01,
        "RISK_TYPE": "fixed",
    },
    "agresif": {
        "LEFT": 15,
        "RIGHT": 10,
        "MANIPULATION_THRESHOLD": 0.001,
        "MAX_CANDLES": 15,
        "CONSECUTIVE_CANDLES": 4,
        "MIN_CANDLES_FOR_SECOND_CONDITION": 15,
        "MAX_CANDLES_FOR_SECOND_CONDITION": 30,
        "RISK_REWARD_RATIO": 1.5,
        "INITIAL_BALANCE": 10000,
        "MAX_RISK": 0.01,
        "RISK_TYPE": "fixed",
    }
}